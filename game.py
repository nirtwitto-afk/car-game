import pygame
import random
import math
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional, Tuple

#
# Initialize Pygame
pygame.init()

# Constants
SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 800
FPS = 60
NUM_LANES = 5
ROAD_WIDTH = SCREEN_WIDTH - 220
ROAD_LEFT_MARGIN = (SCREEN_WIDTH - ROAD_WIDTH) // 2
LANE_WIDTH = ROAD_WIDTH // NUM_LANES
BACKGROUND_COLOR = (0, 0, 0)
ROAD_COLOR = (50, 50, 60)  # Gray-black road
LANE_LINE_COLOR = (255, 255, 255)
CAR_SCREEN_Y = SCREEN_HEIGHT - 150  # Camera keeps car at this Y position

# Game states
class GameState(Enum):
    MENU = 1
    GAME = 2
    SHOP = 3
    GAME_OVER = 4

# Car types
class CarType(Enum):
    DEFAULT = 0
    TELEPORTER = 1
    GHOST = 2
    BIG_RIG = 3
    ENDURANCE = 4

@dataclass
class CarData:
    car_type: CarType
    name: str
    cost: int
    description: str
    ability: str

CAR_DATA = {
    CarType.DEFAULT: CarData(CarType.DEFAULT, "Default Car", 0, "No special abilities", "None"),
    CarType.TELEPORTER: CarData(CarType.TELEPORTER, "Teleporter", 1000, "Teleport past nearest car (E)", "Active"),
    CarType.GHOST: CarData(CarType.GHOST, "Ghost", 2500, "Pass through cars for 5s (E)", "Active"),
    CarType.BIG_RIG: CarData(CarType.BIG_RIG, "Big Rig", 5000, "2x Money multiplier, slower", "Passive"),
    CarType.ENDURANCE: CarData(CarType.ENDURANCE, "Endurance", 7500, "20s brake time", "Passive"),
}

class Player:
    def __init__(self, car_type: CarType = CarType.DEFAULT):
        self.car_type = car_type
        self.x = SCREEN_WIDTH // 2  # Center of screen
        self.y = SCREEN_HEIGHT - 120
        self.speed = 5  # Base auto-forward speed
        self.max_speed = 12 if car_type == CarType.BIG_RIG else 15
        self.acceleration = 0.3
        self.brake_power = 0.4
        self.lateral_speed = 0  # Horizontal movement speed
        self.max_lateral_speed = 3.7  # Slightly faster lane gliding
        self.lateral_acceleration = 0.18  # Smoother, slightly snappier lane changes
        self.max_brake_time = 5
        self.brake_time_used = 0
        self.next_brake_bonus_distance = 500 if car_type == CarType.ENDURANCE else 2500
        self.width = 100 if car_type == CarType.BIG_RIG else 95  # Bigger cars - can't fit between two
        self.height = 140 if car_type == CarType.BIG_RIG else 135
        
        # Ability tracking
        self.ability_cooldown = 0
        self.ghost_active = False
        self.ghost_duration = 0
        self.ghost_overlapping_cars = set()  # Track which cars we're overlapping
        
        # Distance and money
        self.distance = 0
        self.money_earned = 0
        
    def update(self, keys, enemies: List['Enemy']):
        # Base auto-forward speed
        base_forward_speed = 5
        
        # Check if player is steering (reduce speed when turning)
        is_steering = False
        
        # Acceleration with W (boost on top of base speed)
        if keys[pygame.K_w]:
            self.speed = min(self.speed + self.acceleration, self.max_speed)
        else:
            # Decelerate, but apply extra penalty if steering
            if is_steering:
                self.speed = max(self.speed - 0.3, base_forward_speed * 0.33)  # 3x slower when turning
            else:
                self.speed = max(self.speed - 0.15, base_forward_speed)
        
        # Braking
        if keys[pygame.K_s]:
            brake_time_available = self.max_brake_time - self.brake_time_used
            if brake_time_available > 0:
                self.speed = max(self.speed - self.brake_power, self.max_speed * 0.1)
                self.brake_time_used += 1 / FPS
        
        # Smooth lateral movement (left/right) - gliding
        if keys[pygame.K_a]:
            self.lateral_speed = max(self.lateral_speed - self.lateral_acceleration, -self.max_lateral_speed)
            is_steering = True
        elif keys[pygame.K_d]:
            self.lateral_speed = min(self.lateral_speed + self.lateral_acceleration, self.max_lateral_speed)
            is_steering = True
        else:
            # Decelerate lateral movement smoothly when key not held
            if self.lateral_speed > 0:
                self.lateral_speed = max(self.lateral_speed - 0.2, 0)
            elif self.lateral_speed < 0:
                self.lateral_speed = min(self.lateral_speed + 0.2, 0)
        
        # Update x position based on lateral speed
        self.x += self.lateral_speed
        
        # Constrain to road bounds
        self.x = max(ROAD_LEFT_MARGIN + self.width // 2 + 10,
                     min(self.x, ROAD_LEFT_MARGIN + ROAD_WIDTH - self.width // 2 - 10))
        
        # Update distance and money
        self.distance += self.speed
        while self.distance >= self.next_brake_bonus_distance:
            if self.car_type == CarType.ENDURANCE:
                self.max_brake_time = min(50, self.max_brake_time + 1)
                self.next_brake_bonus_distance += 500
            else:
                self.max_brake_time = min(10, self.max_brake_time + 1)
                self.next_brake_bonus_distance += 2500
        multiplier = 2.0 if self.car_type == CarType.BIG_RIG else 1.0
        self.money_earned = int(self.distance * multiplier * 0.1)
        
        # Update ghost ability
        if self.ghost_active:
            self.ghost_duration -= 1 / FPS
            if self.ghost_duration <= 0:
                self.ghost_active = False
                self.ghost_overlapping_cars.clear()
            else:
                # Check which cars we're currently overlapping
                current_overlaps = set()
                for i, enemy in enumerate(enemies):
                    if self.check_collision(enemy):
                        current_overlaps.add(i)
                self.ghost_overlapping_cars = current_overlaps
        
        # Update ability cooldown
        if self.ability_cooldown > 0:
            self.ability_cooldown -= 1 / FPS
        else:
            self.ability_cooldown = 0
    
    def use_ability(self, enemies: List['Enemy']):
        if self.ability_cooldown > 0:
            return False
        
        if self.car_type == CarType.TELEPORTER:
            # Find nearest car ahead
            nearest_enemy = None
            nearest_distance = float('inf')
            for enemy in enemies:
                if enemy.y < self.y:  # Ahead of player
                    dist = self.y - enemy.y
                    if dist < nearest_distance:
                        nearest_distance = dist
                        nearest_enemy = enemy
            
            if nearest_enemy:
                self.y = nearest_enemy.y - 150
                self.ability_cooldown = 10
                # Return True to signal ability was used (for visual effects)
                return True
        
        elif self.car_type == CarType.GHOST:
            self.ghost_active = True
            self.ghost_duration = 5
            self.ghost_overlapping_cars.clear()
            self.ability_cooldown = 15
            return True
        
        return False
    
    def check_collision(self, enemy: 'Enemy') -> bool:
        if self.ghost_active:
            return False
        
        rect1 = pygame.Rect(self.x - self.width // 2, self.y - self.height // 2, self.width, self.height)
        rect2 = pygame.Rect(enemy.x - enemy.width // 2, enemy.y - enemy.height // 2, enemy.width, enemy.height)
        return rect1.colliderect(rect2)
    
    def draw(self, surface):
        # Determine base color based on ghost state
        if self.ghost_active:
            body_color = (150, 100, 200)
            accent_color = (200, 150, 255)
        else:
            body_color = (0, 180, 0)
            accent_color = (0, 255, 0)
        
        # Draw main car body
        rect = pygame.Rect(self.x - self.width // 2, self.y - self.height // 2, self.width, self.height)
        pygame.draw.rect(surface, body_color, rect, border_radius=4)
        
        # Draw darker roof/top section
        roof_color = tuple(max(0, c - 50) for c in (body_color[0], body_color[1], body_color[2]))
        roof_height = self.height // 3
        pygame.draw.rect(surface, roof_color, 
                        (self.x - self.width // 2.5, self.y - self.height // 3, self.width // 1.25, roof_height), 
                        border_radius=3)
        
        # Draw windows
        window_color = (150, 200, 255)
        # Front window
        pygame.draw.rect(surface, window_color, 
                        (self.x - self.width // 2.8, self.y - self.height // 2.5, self.width // 1.4, self.height // 5))
        # Side windows
        pygame.draw.rect(surface, window_color, 
                        (self.x - self.width // 2.2, self.y - self.height // 6, self.width // 3.5, self.height // 4))
        pygame.draw.rect(surface, window_color, 
                        (self.x + self.width // 3.5, self.y - self.height // 6, self.width // 3.5, self.height // 4))
        
        # Draw headlights
        light_color = (255, 255, 150)
        pygame.draw.circle(surface, light_color, (int(self.x - self.width // 4), int(self.y + self.height // 2 - 10)), 5)
        pygame.draw.circle(surface, light_color, (int(self.x + self.width // 4), int(self.y + self.height // 2 - 10)), 5)
        
        # Draw bumper
        pygame.draw.line(surface, (0, 0, 0), 
                        (self.x - self.width // 2, self.y + self.height // 2 - 5),
                        (self.x + self.width // 2, self.y + self.height // 2 - 5), 3)
        
        # Draw outline
        pygame.draw.rect(surface, accent_color, rect, 2)

class Enemy:
    def __init__(self, lane: int, y: float, is_big: bool = False):
        self.lane = lane
        self.x = ROAD_LEFT_MARGIN + lane * LANE_WIDTH + LANE_WIDTH // 2
        self.y = y
        self.speed = random.uniform(2, 5)  # Slower than player base speed
        self.is_big = is_big
        self.width = int(80 * 1.5) if is_big else 80  # Bigger cars appear every few spawns
        self.height = int(120 * 2.0) if is_big else 120
        # Generate realistic camo color
        base_color = random.choice([
            (100, 150, 100),  # Green
            (150, 120, 80),   # Brown
            (120, 120, 120),  # Gray
            (150, 100, 100),  # Red-brown
            (100, 100, 150),  # Blue-gray
        ])
        self.color = tuple(max(0, min(255, c + random.randint(-20, 20))) for c in base_color)
    
    def update(self, player_speed: float):
        # Move slower than player
        self.y += self.speed
    
    def draw(self, surface):
        rect = pygame.Rect(self.x - self.width // 2, self.y - self.height // 2, self.width, self.height)
        
        # Draw main body
        pygame.draw.rect(surface, self.color, rect, border_radius=4)
        
        # Draw darker roof/top section
        roof_color = tuple(max(0, c - 50) for c in self.color)
        roof_height = self.height // 3
        pygame.draw.rect(surface, roof_color, 
                        (self.x - self.width // 2.5, self.y - self.height // 3, self.width // 1.25, roof_height), 
                        border_radius=3)
        
        # Draw windows
        window_color = (100, 150, 200)
        # Front window
        pygame.draw.rect(surface, window_color, 
                        (self.x - self.width // 2.8, self.y - self.height // 2.5, self.width // 1.4, self.height // 5))
        # Side windows
        pygame.draw.rect(surface, window_color, 
                        (self.x - self.width // 2.2, self.y - self.height // 6, self.width // 3.5, self.height // 4))
        pygame.draw.rect(surface, window_color, 
                        (self.x + self.width // 3.5, self.y - self.height // 6, self.width // 3.5, self.height // 4))
        
        # Draw headlights
        light_color = (255, 255, 150)
        pygame.draw.circle(surface, light_color, (int(self.x - self.width // 4), int(self.y + self.height // 2 - 10)), 4)
        pygame.draw.circle(surface, light_color, (int(self.x + self.width // 4), int(self.y + self.height // 2 - 10)), 4)
        
        # Draw bumper
        pygame.draw.line(surface, (0, 0, 0), 
                        (self.x - self.width // 2, self.y + self.height // 2 - 5),
                        (self.x + self.width // 2, self.y + self.height // 2 - 5), 3)
        
        # Draw camo spots
        camo_color = tuple(max(0, c - 40) for c in self.color)
        for i in range(2):
            spot_x = int(self.x - self.width // 4 + (i % 2) * self.width // 2)
            spot_y = int(self.y - self.height // 6 + (i // 2) * self.height // 3)
            pygame.draw.circle(surface, camo_color, (spot_x, spot_y), 5)
        
        # Draw outline
        pygame.draw.rect(surface, (255, 255, 255), rect, 2)
    
    def is_offscreen(self) -> bool:
        return self.y > SCREEN_HEIGHT

class Game:
    def __init__(self):
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Top-Down Driving Game")
        self.clock = pygame.time.Clock()
        self.font_large = pygame.font.Font(None, 48)
        self.font_medium = pygame.font.Font(None, 36)
        self.font_small = pygame.font.Font(None, 24)
        
        self.state = GameState.MENU
        self.player = None
        self.enemies: List[Enemy] = []
        self.total_money = 0  # Total accumulated money
        self.owned_cars = {CarType.DEFAULT}
        self.current_car = CarType.DEFAULT
        self.enemy_spawn_timer = 0
        self.enemy_spawn_rate = 60
        self.enemy_spawn_count = 0
        self.next_big_enemy_in = random.randint(4, 10)
        self.lane_line_offset = 0
        self.selected_menu_item = 0
        self.selected_shop_item = 0
        self.camera_y = 0  # Camera position for following car
        self.ability_effect_timer = 0  # For visual effect timing
        
        self.run()
    
    def handle_input(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            
            if event.type == pygame.KEYDOWN:
                if self.state == GameState.MENU:
                    if event.key == pygame.K_UP:
                        self.selected_menu_item = max(0, self.selected_menu_item - 1)
                    elif event.key == pygame.K_DOWN:
                        self.selected_menu_item = min(1, self.selected_menu_item + 1)
                    elif event.key == pygame.K_RETURN:
                        if self.selected_menu_item == 0:
                            self.start_game()
                        else:
                            self.state = GameState.SHOP
                            self.selected_shop_item = 0
                
                elif self.state == GameState.SHOP:
                    if event.key == pygame.K_UP:
                        self.selected_shop_item = max(0, self.selected_shop_item - 3)
                    elif event.key == pygame.K_DOWN:
                        self.selected_shop_item = min(4, self.selected_shop_item + 3)
                    elif event.key == pygame.K_LEFT:
                        if self.selected_shop_item % 3 > 0:
                            self.selected_shop_item -= 1
                    elif event.key == pygame.K_RIGHT:
                        if self.selected_shop_item % 3 < 2 and self.selected_shop_item < 4:
                            self.selected_shop_item += 1
                    elif event.key == pygame.K_RETURN:
                        self.handle_shop_purchase()
                    elif event.key == pygame.K_ESCAPE:
                        self.state = GameState.MENU
                        self.selected_menu_item = 0
                
                elif self.state == GameState.GAME:
                    if event.key == pygame.K_e:
                        self.player.use_ability(self.enemies)
                
                elif self.state == GameState.GAME_OVER:
                    if event.key == pygame.K_RETURN:
                        self.state = GameState.MENU
                        self.selected_menu_item = 0
                    elif event.key == pygame.K_ESCAPE:
                        return False
        
        return True
    
    def start_game(self):
        self.state = GameState.GAME
        self.player = Player(self.current_car)
        self.enemies = []
        self.enemy_spawn_timer = 0
    
    def handle_shop_purchase(self):
        cars = list(CarType)
        if 0 <= self.selected_shop_item < len(cars):
            car_type = cars[self.selected_shop_item]
            if car_type in self.owned_cars:
                # Equip car
                self.current_car = car_type
            else:
                # Buy car
                cost = CAR_DATA[car_type].cost
                if self.total_money >= cost:
                    self.total_money -= cost
                    self.owned_cars.add(car_type)
                    self.current_car = car_type
    
    def spawn_enemies(self):
        self.enemy_spawn_timer += 1
        spawn_rate = self.enemy_spawn_rate
        if self.player and self.player.speed >= self.player.max_speed * 0.99:
            spawn_rate = int(self.enemy_spawn_rate * 0.7)
        if self.enemy_spawn_timer >= spawn_rate:
            self.enemy_spawn_timer = 0
            
            # Ensure "always solvable" - at least one lane must be clear
            # Spawn strategy: randomly choose 1-4 lanes, ensure at least 1 is free
            lanes_to_spawn = random.randint(1, min(4, NUM_LANES - 1))
            available_lanes = list(range(NUM_LANES))
            lanes_spawned = random.sample(available_lanes, lanes_to_spawn)
            
            should_spawn_big = self.enemy_spawn_count >= self.next_big_enemy_in
            if should_spawn_big:
                self.enemy_spawn_count = 0
                self.next_big_enemy_in = random.randint(4, 10)
            else:
                self.enemy_spawn_count += 1
            
            big_lane = random.choice(lanes_spawned) if should_spawn_big else None
            for lane in lanes_spawned:
                enemy = Enemy(lane, -80, is_big=(lane == big_lane))
                self.enemies.append(enemy)
    
    def update_game(self):
        if self.state != GameState.GAME or not self.player:
            return
        
        keys = pygame.key.get_pressed()
        self.player.update(keys, self.enemies)
        
        for enemy in self.enemies:
            enemy.update(self.player.speed)
        
        # Remove offscreen enemies
        self.enemies = [e for e in self.enemies if not e.is_offscreen()]
        
        # Collision detection
        for i, enemy in enumerate(self.enemies):
            if self.player.check_collision(enemy):
                # Check if in ghost mode
                if self.player.ghost_active:
                    # Check if currently overlapping with this specific car
                    if i in self.player.ghost_overlapping_cars:
                        # Overlapping, check if still ghosting
                        if self.player.ghost_duration > 0:
                            continue  # Safe, keep ghost active
                    else:
                        # Not overlapping, safe
                        continue
                
                # Game over
                self.state = GameState.GAME_OVER
                self.total_money += self.player.money_earned
                return
        
        # Spawn enemies
        self.spawn_enemies()
        
        # Update lane lines
        self.lane_line_offset = (self.lane_line_offset + self.player.speed) % 40
    
    def draw_road(self):
        self.screen.fill(ROAD_COLOR)
        
        # Draw dirt and background
        dirt_color = (101, 67, 33)
        pygame.draw.rect(self.screen, dirt_color, (0, 0, SCREEN_WIDTH, SCREEN_HEIGHT))
        
        # Draw road surface
        pygame.draw.rect(self.screen, ROAD_COLOR, (ROAD_LEFT_MARGIN, 0, ROAD_WIDTH, SCREEN_HEIGHT))
        
        # Draw brick walls on edges
        brick_color = (139, 69, 19)
        brick_dark = (101, 50, 15)
        wall_width = 30
        
        # Left wall
        for y in range(0, SCREEN_HEIGHT + 40, 40):
            for x in range(0, wall_width, 20):
                # Brick pattern
                if (y // 40 + x // 20) % 2 == 0:
                    pygame.draw.rect(self.screen, brick_color, (x, y, 19, 38))
                else:
                    pygame.draw.rect(self.screen, brick_dark, (x, y, 19, 38))
                pygame.draw.rect(self.screen, (50, 50, 50), (x, y, 19, 38), 1)
        
        # Right wall
        for y in range(0, SCREEN_HEIGHT + 40, 40):
            for x in range(SCREEN_WIDTH - wall_width, SCREEN_WIDTH, 20):
                # Brick pattern
                if (y // 40 + (x - (SCREEN_WIDTH - wall_width)) // 20) % 2 == 0:
                    pygame.draw.rect(self.screen, brick_color, (x, y, 19, 38))
                else:
                    pygame.draw.rect(self.screen, brick_dark, (x, y, 19, 38))
                pygame.draw.rect(self.screen, (50, 50, 50), (x, y, 19, 38), 1)
        
        # Draw stationary bushes and plants
        bush_color = (30, 100, 30)
        light_bush_color = (50, 130, 50)
        
        # Left side bushes (stationary positions)
        for y_base in range(0, SCREEN_HEIGHT, 150):
            y = y_base
            # Group of bushes
            pygame.draw.circle(self.screen, bush_color, (ROAD_LEFT_MARGIN - 20, y + 50), 14)
            pygame.draw.circle(self.screen, light_bush_color, (ROAD_LEFT_MARGIN - 14, y + 60), 12)
            pygame.draw.circle(self.screen, bush_color, (ROAD_LEFT_MARGIN - 26, y + 60), 11)
        
        # Right side bushes (stationary positions)
        for y_base in range(0, SCREEN_HEIGHT, 150):
            y = y_base
            # Group of bushes
            pygame.draw.circle(self.screen, bush_color, (ROAD_LEFT_MARGIN + ROAD_WIDTH + 18, y + 50), 14)
            pygame.draw.circle(self.screen, light_bush_color, (ROAD_LEFT_MARGIN + ROAD_WIDTH + 24, y + 60), 12)
            pygame.draw.circle(self.screen, bush_color, (ROAD_LEFT_MARGIN + ROAD_WIDTH + 12, y + 60), 11)
        
        # Draw lane divider lines (thicker)
        for i in range(1, NUM_LANES):
            x = ROAD_LEFT_MARGIN + i * LANE_WIDTH
            # Draw dashed lines
            dash_length = 25
            gap_length = 25
            y = self.lane_line_offset
            while y < SCREEN_HEIGHT:
                pygame.draw.line(self.screen, LANE_LINE_COLOR, (x, y), (x, y + dash_length), 4)  # Thicker
                y += dash_length + gap_length
    
    def draw_hud(self):
        if not self.player:
            return
        
        hud_x = 20
        hud_y = 20
        hud_width = 300
        hud_height = 280
        
        # HUD background with transparent overlay.
        panel_surface = pygame.Surface((hud_width + 10, hud_height + 10), pygame.SRCALPHA)
        panel_surface.fill((0, 0, 0, 0))
        self.screen.blit(panel_surface, (hud_x - 5, hud_y - 5))
        
        # Title
        title = self.font_medium.render("STATUS", True, (100, 255, 100))
        self.screen.blit(title, (hud_x + 10, hud_y + 5))
        
        # Draw a line separator
        pygame.draw.line(self.screen, (100, 200, 50), (hud_x + 10, hud_y + 45), (hud_x + hud_width - 15, hud_y + 45), 2)
        
        current_y = hud_y + 60
        line_height = 38
        
        # Speed bar
        speed_label = self.font_small.render(f"SPEED", True, (255, 255, 0))
        self.screen.blit(speed_label, (hud_x + 10, current_y))
        speed_percent = int((self.player.speed / self.player.max_speed) * 100)
        bar_width = 200
        pygame.draw.rect(self.screen, (50, 50, 50), (hud_x + 100, current_y + 2, bar_width, 20))
        pygame.draw.rect(self.screen, (0, 255, 0), (hud_x + 100, current_y + 2, int(bar_width * speed_percent / 100), 20))
        speed_text = self.font_small.render(f"{speed_percent}%", True, (255, 255, 255))
        self.screen.blit(speed_text, (hud_x + 305, current_y + 2))
        current_y += line_height
        
        # Distance
        dist_text = self.font_small.render(f"Distance: {int(self.player.distance)}", True, (255, 255, 255))
        self.screen.blit(dist_text, (hud_x + 10, current_y))
        current_y += line_height
        
        # Money earned this run
        money_text = self.font_small.render(f"Earned: ${self.player.money_earned}", True, (100, 255, 100))
        self.screen.blit(money_text, (hud_x + 10, current_y))
        current_y += line_height
        
        # Total money
        total_text = self.font_small.render(f"Total: ${self.total_money}", True, (255, 215, 0))
        self.screen.blit(total_text, (hud_x + 10, current_y))
        current_y += line_height
        
        # Brake time
        brake_time_left = self.player.max_brake_time - self.player.brake_time_used
        brake_percent = int((brake_time_left / self.player.max_brake_time) * 100)
        brake_label = self.font_small.render(f"BRAKE", True, (255, 100, 100))
        self.screen.blit(brake_label, (hud_x + 10, current_y))
        pygame.draw.rect(self.screen, (50, 50, 50), (hud_x + 100, current_y + 2, bar_width, 20))
        pygame.draw.rect(self.screen, (255, 100, 100), (hud_x + 100, current_y + 2, int(bar_width * brake_percent / 100), 20))
        brake_text = self.font_small.render(f"{brake_time_left:.1f}s", True, (255, 255, 255))
        self.screen.blit(brake_text, (hud_x + 305, current_y + 2))
        current_y += line_height
        
        # Ability status
        if self.player.ability_cooldown > 0:
            ability_text = self.font_small.render(f"Ability: {self.player.ability_cooldown:.1f}s", True, (200, 100, 255))
        elif self.player.car_type in [CarType.TELEPORTER, CarType.GHOST]:
            ability_text = self.font_small.render(f"Ability: Ready (E)", True, (0, 255, 255))
        else:
            ability_text = self.font_small.render(f"Ability: None", True, (150, 150, 150))
        self.screen.blit(ability_text, (hud_x + 10, current_y))
    
    def draw_car_preview(self, x, y, car_type: CarType):
        """Draw a preview of a car in the shop"""
        width = 60
        height = 90
        
        # Determine color based on car type
        if car_type == CarType.DEFAULT:
            body_color = (0, 180, 0)
            accent_color = (0, 255, 0)
        elif car_type == CarType.TELEPORTER:
            body_color = (0, 100, 200)
            accent_color = (0, 150, 255)
        elif car_type == CarType.GHOST:
            body_color = (150, 100, 200)
            accent_color = (200, 150, 255)
        elif car_type == CarType.BIG_RIG:
            body_color = (150, 100, 50)
            accent_color = (200, 150, 100)
        elif car_type == CarType.ENDURANCE:
            body_color = (150, 0, 0)
            accent_color = (255, 0, 0)
        
        # Draw main car body
        rect = pygame.Rect(x - width // 2, y - height // 2, width, height)
        pygame.draw.rect(self.screen, body_color, rect, border_radius=3)
        
        # Draw darker roof
        roof_color = tuple(max(0, c - 50) for c in (body_color[0], body_color[1], body_color[2]))
        pygame.draw.rect(self.screen, roof_color, 
                        (x - width // 2.5, y - height // 3, width // 1.25, height // 3), 
                        border_radius=2)
        
        # Draw windows
        window_color = (150, 200, 255)
        pygame.draw.rect(self.screen, window_color, 
                        (x - width // 2.8, y - height // 2.5, width // 1.4, height // 5))
        
        # Draw headlights
        light_color = (255, 255, 100)
        pygame.draw.circle(self.screen, light_color, (int(x - width // 4), int(y + height // 2 - 5)), 3)
        pygame.draw.circle(self.screen, light_color, (int(x + width // 4), int(y + height // 2 - 5)), 3)
        
        # Draw outline
        pygame.draw.rect(self.screen, accent_color, rect, 2)
    
    def draw_menu(self):
        # Gradient background
        for y in range(SCREEN_HEIGHT):
            color_val = int(20 + (y / SCREEN_HEIGHT) * 40)
            pygame.draw.line(self.screen, (color_val, color_val, color_val + 30), (0, y), (SCREEN_WIDTH, y))
        
        # Draw decorative road lines in background
        for i in range(1, NUM_LANES):
            x = i * LANE_WIDTH
            for y in range(0, SCREEN_HEIGHT, 40):
                pygame.draw.line(self.screen, (50, 50, 60), (x, y), (x, y + 20), 1)
        
        # Title with glow effect
        title = self.font_large.render("DRIVE GAME", True, (0, 255, 100))
        title_shadow = self.font_large.render("DRIVE GAME", True, (0, 100, 50))
        title_rect = title.get_rect(center=(SCREEN_WIDTH // 2, 80))
        title_shadow_rect = title_shadow.get_rect(center=(SCREEN_WIDTH // 2 + 3, 83))
        self.screen.blit(title_shadow, title_shadow_rect)
        self.screen.blit(title, title_rect)
        
        # Draw menu items with better styling
        menu_items = ["Start Game", "Shop"]
        for i, item in enumerate(menu_items):
            y_pos = 300 + i * 120
            
            if i == self.selected_menu_item:
                # Highlighted box
                pygame.draw.rect(self.screen, (0, 200, 100), (SCREEN_WIDTH // 2 - 200, y_pos - 40, 400, 80), border_radius=10)
                pygame.draw.rect(self.screen, (0, 255, 150), (SCREEN_WIDTH // 2 - 200, y_pos - 40, 400, 80), 3)
                color = (0, 0, 0)
            else:
                # Normal box
                pygame.draw.rect(self.screen, (40, 40, 60), (SCREEN_WIDTH // 2 - 200, y_pos - 40, 400, 80), border_radius=10)
                pygame.draw.rect(self.screen, (100, 100, 150), (SCREEN_WIDTH // 2 - 200, y_pos - 40, 400, 80), 2)
                color = (200, 200, 200)
            
            surface = self.font_medium.render(item, True, color)
            rect = surface.get_rect(center=(SCREEN_WIDTH // 2, y_pos))
            self.screen.blit(surface, rect)
        
        # Info panel at bottom
        info_box_height = 80
        pygame.draw.rect(self.screen, (30, 30, 45), (0, SCREEN_HEIGHT - info_box_height, SCREEN_WIDTH, info_box_height))
        pygame.draw.line(self.screen, (100, 200, 100), (0, SCREEN_HEIGHT - info_box_height), (SCREEN_WIDTH, SCREEN_HEIGHT - info_box_height), 2)
        
        total_text = self.font_medium.render(f"Total Money: ${self.total_money}", True, (100, 255, 100))
        total_rect = total_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 50))
        self.screen.blit(total_text, total_rect)
        
        cars_owned = self.font_small.render(f"Cars Owned: {len(self.owned_cars)}/5", True, (150, 150, 200))
        cars_rect = cars_owned.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 20))
        self.screen.blit(cars_owned, cars_rect)
        
        # Arrow indicator
        if self.selected_menu_item == 0:
            arrow_y = 300
        else:
            arrow_y = 420
        arrow_text = self.font_medium.render(">", True, (0, 255, 150))
        self.screen.blit(arrow_text, (SCREEN_WIDTH // 2 - 240, arrow_y - 20))
        self.screen.blit(arrow_text, (SCREEN_WIDTH // 2 + 220, arrow_y - 20))
    
    def draw_shop(self):
        self.screen.fill(BACKGROUND_COLOR)
        
        # Gradient background
        for y in range(SCREEN_HEIGHT):
            color_val = int(20 + (y / SCREEN_HEIGHT) * 40)
            pygame.draw.line(self.screen, (color_val, color_val, color_val + 30), (0, y), (SCREEN_WIDTH, y))
        
        title = self.font_large.render("SHOP", True, (200, 100, 0))
        title_rect = title.get_rect(center=(SCREEN_WIDTH // 2, 30))
        self.screen.blit(title, title_rect)
        
        # Draw car previews in a grid
        cars = list(CarType)
        cols = 3
        rows = 2
        
        preview_width = 280
        preview_height = 280
        start_x = 50
        start_y = 100
        spacing_x = 380
        spacing_y = 340
        
        for i, car_type in enumerate(cars):
            row = i // cols
            col = i % cols
            if row >= rows:
                break
            
            x = start_x + col * spacing_x
            y = start_y + row * spacing_y
            
            data = CAR_DATA[car_type]
            
            # Draw preview box
            is_selected = (i == self.selected_shop_item)
            if is_selected:
                pygame.draw.rect(self.screen, (0, 200, 100), (x - 10, y - 10, preview_width + 20, preview_height + 20), border_radius=15)
                pygame.draw.rect(self.screen, (0, 255, 150), (x - 10, y - 10, preview_width + 20, preview_height + 20), 3)
            else:
                pygame.draw.rect(self.screen, (40, 40, 60), (x - 10, y - 10, preview_width + 20, preview_height + 20), border_radius=15)
                pygame.draw.rect(self.screen, (100, 100, 150), (x - 10, y - 10, preview_width + 20, preview_height + 20), 2)
            
            pygame.draw.rect(self.screen, (20, 20, 30), (x, y, preview_width, preview_height), border_radius=10)
            
            # Draw car preview
            self.draw_car_preview(x + preview_width // 2, y + 80, car_type)
            
            # Draw car name
            name_color = (0, 255, 0) if car_type in self.owned_cars else (255, 255, 255)
            name_text = self.font_medium.render(data.name, True, name_color)
            name_rect = name_text.get_rect(center=(x + preview_width // 2, y + 180))
            self.screen.blit(name_text, name_rect)
            
            # Draw description
            desc_text = self.font_small.render(data.description, True, (200, 200, 200))
            desc_rect = desc_text.get_rect(center=(x + preview_width // 2, y + 220))
            self.screen.blit(desc_text, desc_rect)
            
            # Draw cost or owned
            if car_type in self.owned_cars:
                if self.current_car == car_type:
                    status = self.font_small.render("[EQUIPPED]", True, (255, 255, 0))
                else:
                    status = self.font_small.render("[OWNED]", True, (0, 255, 0))
            else:
                status = self.font_small.render(f"${data.cost}", True, (255, 100, 100))
            status_rect = status.get_rect(center=(x + preview_width // 2, y + 250))
            self.screen.blit(status, status_rect)
        
        # Info at bottom
        info_box_height = 60
        pygame.draw.rect(self.screen, (30, 30, 45), (0, SCREEN_HEIGHT - info_box_height, SCREEN_WIDTH, info_box_height))
        pygame.draw.line(self.screen, (100, 200, 100), (0, SCREEN_HEIGHT - info_box_height), (SCREEN_WIDTH, SCREEN_HEIGHT - info_box_height), 2)
        
        money_text = self.font_medium.render(f"Current Money: ${self.total_money}", True, (100, 255, 100))
        money_rect = money_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 35))
        self.screen.blit(money_text, money_rect)
        
        esc_text = self.font_small.render("ESC to go back | UP/DOWN to select | ENTER to buy/equip", True, (100, 100, 100))
        esc_rect = esc_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 15))
        self.screen.blit(esc_text, esc_rect)
    
    def draw_game_over(self):
        # Semi-transparent overlay
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        overlay.set_alpha(180)
        overlay.fill((0, 0, 0))
        self.screen.blit(overlay, (0, 0))
        
        game_over = self.font_large.render("GAME OVER", True, (255, 0, 0))
        game_over_rect = game_over.get_rect(center=(SCREEN_WIDTH // 2, 150))
        self.screen.blit(game_over, game_over_rect)
        
        if self.player:
            distance_text = self.font_medium.render(f"Distance: {int(self.player.distance)}", True, (255, 255, 255))
            distance_rect = distance_text.get_rect(center=(SCREEN_WIDTH // 2, 250))
            self.screen.blit(distance_text, distance_rect)
            
            money_text = self.font_medium.render(f"Money Earned: ${self.player.money_earned}", True, (100, 200, 100))
            money_rect = money_text.get_rect(center=(SCREEN_WIDTH // 2, 320))
            self.screen.blit(money_text, money_rect)
            
            total_text = self.font_medium.render(f"Total Money: ${self.total_money}", True, (0, 200, 0))
            total_rect = total_text.get_rect(center=(SCREEN_WIDTH // 2, 390))
            self.screen.blit(total_text, total_rect)
        
        continue_text = self.font_small.render("Press ENTER to continue", True, (200, 200, 200))
        continue_rect = continue_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 50))
        self.screen.blit(continue_text, continue_rect)
    
    def draw(self):
        if self.state == GameState.GAME:
            self.draw_road()
            for enemy in self.enemies:
                enemy.draw(self.screen)
            if self.player:
                self.player.draw(self.screen)
            self.draw_hud()
        elif self.state == GameState.MENU:
            self.draw_menu()
        elif self.state == GameState.SHOP:
            self.draw_shop()
        elif self.state == GameState.GAME_OVER:
            self.draw_road()
            for enemy in self.enemies:
                enemy.draw(self.screen)
            if self.player:
                self.player.draw(self.screen)
            self.draw_game_over()
        
        pygame.display.flip()
    
    def run(self):
        running = True
        while running:
            running = self.handle_input()
            self.update_game()
            self.draw()
            self.clock.tick(FPS)
        
        pygame.quit()

if __name__ == "__main__":
    game = Game()
