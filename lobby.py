import sys
import math
import random
import pygame
import numpy as np
import json
from pygame import Vector2

# Settings
WIDTH, HEIGHT = 960, 640
WORLD_WIDTH, WORLD_HEIGHT = 1920, 1280  # Larger world size
FPS = 120
BG_COLOR = (18, 20, 28)
GRID_COLOR = (40, 42, 58)
CELL_SIZE = 50

# Game States
STATE_MENU = 0
STATE_MODE_SELECT = 1
STATE_PLAYING = 2
STATE_SHOP = 3
STATE_GAMEOVER = 4

# UI Colors
BULLET_COLOR = (255, 230, 140)
BUTTON_COLOR = (60, 65, 80)
BUTTON_HOVER_COLOR = (80, 85, 100)
TEXT_COLOR = (255, 255, 255)
CURRENCY_COLOR = (255, 215, 0)
ERROR_COLOR = (255, 80, 80)
INFO_COLOR = (140, 140, 140)

FONT_PATH = "BaiJamjuree-Bold.ttf"

WEAPONS = {
    "Pistol": {
        "price": 0,
        "fire_rate": 0.16,
        "bullet_damage": 1,
        "name": "Pistol"
    },
    "Machine Gun": {
        "price": 200,
        "fire_rate": 0.08,
        "bullet_damage": 1,
        "name": "Machine Gun"
    },
    "Shotgun": {
        "price": 500,
        "fire_rate": 0.5,
        "bullet_damage": 2,  # Each pellet
        "pellets": 5,  # Shoots multiple pellets
        "name": "Shotgun"
    },
    "Sniper Rifle": {
        "price": 1200,
        "fire_rate": 1.2,
        "bullet_damage": 15,
        "name": "Sniper Rifle"
    },
    "Rocket Launcher": {
        "price": 3000,
        "fire_rate": 3.0,
        "bullet_damage": 30, # AoE damage
        "name": "Rocket Launcher"
    }
}


def clamp(x, a, b):
    return max(a, min(b, x))

def clamp01(x):
    return clamp(x, 0.0, 1.0)

def create_beep_sound(frequency=440, duration_ms=100, volume=0.15):
    sample_rate = 44100
    n_samples = int(sample_rate * duration_ms / 1000)
    t = np.linspace(0, duration_ms / 1000, n_samples, False)
    wave = np.sin(2 * np.pi * frequency * t)
    wave = (wave * 32767 * volume).astype(np.int16)
    stereo_wave = np.column_stack((wave, wave))
    sound = pygame.sndarray.make_sound(stereo_wave)
    return sound

class SaveManager:
    def __init__(self, save_file="save.json"):
        self.save_file = save_file

    def save_game(self, data):
        try:
            with open(self.save_file, 'w') as f:
                json.dump(data, f, indent=4)
        except IOError as e:
            print(f"Could not save game: {e}")

    def load_game(self):
        try:
            with open(self.save_file, 'r') as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError):
            print("No save file found or file is corrupted. Starting a new game.")
            return {"currency": 0, "weapons_owned": ["Pistol"]}

class Particle:
    def __init__(self, pos, vel, size, color, lifetime):
        self.pos = Vector2(pos)
        self.vel = Vector2(vel)
        self.size = size
        self.color = color
        self.lifetime = lifetime
        self.age = 0.0

    def update(self, dt):
        self.age += dt
        self.pos += self.vel * dt
        self.vel *= 0.9

    def draw(self, surf, camera):
        t = clamp01(1 - (self.age / self.lifetime))
        if t <= 0:
            return
        a = int(255 * t)
        col = (*self.color[:3], a) if len(self.color) == 4 else (*self.color, a)
        s = int(max(1, self.size * t))
        surf_r = pygame.Surface((s*2, s*2), pygame.SRCALPHA)
        pygame.draw.circle(surf_r, col, (s, s), s)

        screen_pos = self.pos - camera
        surf.blit(surf_r, (screen_pos.x - s, screen_pos.y - s))

    def is_dead(self):
        return self.age >= self.lifetime

class Bullet:
    def __init__(self, pos, dir, damage):
        self.pos = Vector2(pos)
        self.vel = Vector2(dir).normalize() * 900
        self.radius = 4
        self.age = 0.0
        self.damage = damage

    def update(self, dt):
        self.pos += self.vel * dt
        self.age += dt

    def draw(self, surf, camera):
        screen_pos = self.pos - camera
        pygame.draw.circle(surf, BULLET_COLOR, (int(screen_pos.x), int(screen_pos.y)), self.radius)

    def is_dead(self):
        if self.age > 1.2:
            return True
        if not (-50 <= self.pos.x <= WORLD_WIDTH+50 and -50 <= self.pos.y <= WORLD_HEIGHT+50):
            return True
        return False

class Player:
    def __init__(self, pos, sprite, save_data):
        self.pos = Vector2(pos)
        self.vel = Vector2(0, 0)
        self.size = sprite.get_width()
        self.health = 100
        self.max_health = 100
        self.score = 0
        self.damage_cooldown = 0.5
        self.damage_timer = 0.0
        self.sprite = sprite

        self.weapons_owned = save_data.get("weapons_owned", ["Pistol"])
        self.currency = save_data.get("currency", 0)
        self.current_weapon_name = self.weapons_owned[0] if self.weapons_owned else "Pistol"
        self.current_weapon = WEAPONS[self.current_weapon_name]
        self.fire_timer = 0.0

    def update(self, dt, keys):
        move = Vector2(0, 0)
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            move.y = -1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            move.y = 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            move.x = -1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            move.x = 1
        if move.length_squared() > 0:
            move = move.normalize()

        target_speed = 380
        accel = 1600
        friction = 10

        target_vel = move * target_speed
        self.vel += (target_vel - self.vel) * clamp01(min(1, accel * dt / max(1, target_speed)))
        if move.length_squared() == 0:
            self.vel *= (1.0 - clamp01(friction * dt * 0.1))

        self.pos += self.vel * dt
        self.pos.x = clamp(self.pos.x, self.size/2, WORLD_WIDTH - self.size/2)
        self.pos.y = clamp(self.pos.y, self.size/2, WORLD_HEIGHT - self.size/2)

        self.fire_timer = max(0.0, self.fire_timer - dt)
        if self.damage_timer > 0:
            self.damage_timer -= dt

    def can_fire(self):
        return self.fire_timer <= 0.0

    def fire(self, mouse_world_pos):
        self.fire_timer = self.current_weapon["fire_rate"]
        bullets = []

        if self.current_weapon_name == "Shotgun":
            pellets = self.current_weapon["pellets"]
            base_dir = (mouse_world_pos - self.pos).normalize()
            for _ in range(pellets):
                angle_offset = random.uniform(-10, 10)
                bullet_dir = base_dir.rotate(angle_offset)
                bullet = Bullet(self.pos, bullet_dir, self.current_weapon["bullet_damage"])
                bullets.append(bullet)
        else:
            bullet_dir = mouse_world_pos - self.pos
            bullet = Bullet(self.pos, bullet_dir, self.current_weapon["bullet_damage"])
            bullets.append(bullet)

        return bullets

    def draw(self, surf, mouse_pos_screen, camera):
        player_screen_pos = self.pos - camera
        direction = mouse_pos_screen - player_screen_pos
        angle = -direction.angle_to(Vector2(1, 0)) if direction.length_squared() > 0 else 0
        rotated_sprite = pygame.transform.rotate(self.sprite, angle)
        rect = rotated_sprite.get_rect(center=(int(player_screen_pos.x), int(player_screen_pos.y)))
        surf.blit(rotated_sprite, rect)

class Enemy:
    def __init__(self, pos, kind, speed, hp, sprite):
        self.pos = Vector2(pos)
        self.kind = kind
        self.speed = speed
        self.hp = hp
        self.sprite = sprite
        self.radius = self.sprite.get_width() // 2
        self.dir = Vector2(0, 0)

    def update(self, dt, player_pos):
        dir_to_player = player_pos - self.pos
        if dir_to_player.length_squared() > 0.1:
            dir_to_player = dir_to_player.normalize()
        wander = Vector2(random.uniform(-0.6, 0.6), random.uniform(-0.6, 0.6))
        self.dir = (dir_to_player * 0.85 + wander * 0.15).normalize()
        self.pos += self.dir * self.speed * dt

    def draw(self, surf, camera):
        screen_pos = self.pos - camera
        rect = self.sprite.get_rect(center=(int(screen_pos.x), int(screen_pos.y)))
        surf.blit(self.sprite, rect)

class Button:
    def __init__(self, rect, text, font, color, hover_color):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.font = font
        self.text_surf = self.font.render(self.text, True, TEXT_COLOR)
        self.text_rect = self.text_surf.get_rect(center=self.rect.center)
        self.color = color
        self.hover_color = hover_color
        self.is_hovered = False

    def draw(self, surf, mouse_pos):
        self.is_hovered = self.rect.collidepoint(mouse_pos)
        color = self.hover_color if self.is_hovered else self.color
        pygame.draw.rect(surf, color, self.rect, border_radius=8)
        self.text_rect.center = self.rect.center
        surf.blit(self.text_surf, self.text_rect)

class Game:
    def __init__(self, screen):
        pygame.mixer.pre_init(frequency=44100, size=-16, channels=2)
        pygame.init()
        pygame.font.init()
        self.font = pygame.font.Font(FONT_PATH, 24)
        self.big_font = pygame.font.Font(FONT_PATH, 48)
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.load_sprites()
        self.camera = Vector2(0, 0)
        self.save_manager = SaveManager()
        self.state = STATE_MENU
        self.load_player_data = self.save_manager.load_game()
        self.player = self.create_player_from_save()
        
        self.main_menu_buttons = []
        self.mode_select_buttons = []
        self.shop_buttons = []
        self.game_over_buttons = []
        self.create_buttons()
        
        self.purchase_error_timer = 0
        self.purchase_error_message = ""
        self.enemies_killed = 0

        self.shoot_sound = create_beep_sound(880, 60, 0.12)
        self.hit_sound = create_beep_sound(320, 90, 0.10)
    
    def create_player_from_save(self):
        return Player((WORLD_WIDTH*0.5, WORLD_HEIGHT*0.7), self.player_sprite, self.load_player_data)
        
    def create_buttons(self):
        w, h = self.screen.get_size()
        button_width = 200
        button_height = 50
        
        # Main menu buttons
        y_start_menu = h // 2 - 60
        button_y_spacing = 60
        self.main_menu_buttons = [
            Button(pygame.Rect(w//2 - button_width//2, y_start_menu, button_width, button_height), "Play", self.font, BUTTON_COLOR, BUTTON_HOVER_COLOR),
            Button(pygame.Rect(w//2 - button_width//2, y_start_menu + button_y_spacing, button_width, button_height), "Shop", self.font, BUTTON_COLOR, BUTTON_HOVER_COLOR),
            Button(pygame.Rect(w//2 - button_width//2, y_start_menu + 2*button_y_spacing, button_width, button_height), "Quit", self.font, BUTTON_COLOR, BUTTON_HOVER_COLOR)
        ]
        
        # Mode select buttons
        y_start_mode = h//2 - 40
        self.mode_select_buttons = [
            Button(pygame.Rect(w//2 - button_width//2, y_start_mode, button_width, button_height), "Infinite Mode", self.font, BUTTON_COLOR, BUTTON_HOVER_COLOR),
            Button(pygame.Rect(w//2 - button_width//2, y_start_mode + button_y_spacing, button_width, button_height), "Levels", self.font, BUTTON_COLOR, BUTTON_HOVER_COLOR)
        ]
        
        # Shop buttons
        self.shop_buttons = []
        y_offset_shop = 180
        button_width_shop = 300
        for name, data in WEAPONS.items():
            button_rect = pygame.Rect(w//2 - button_width_shop//2, y_offset_shop, button_width_shop, button_height)
            button = Button(button_rect, name, self.font, BUTTON_COLOR, BUTTON_HOVER_COLOR)
            self.shop_buttons.append(button)
            y_offset_shop += 80
        # Add back to menu button to shop
        back_button_rect = pygame.Rect(w//2 - button_width//2, h - 70, button_width, button_height)
        self.shop_buttons.append(Button(back_button_rect, "Back to Menu", self.font, BUTTON_COLOR, BUTTON_HOVER_COLOR))

        # Game over buttons
        self.game_over_buttons = [
            Button(pygame.Rect(w//2 - button_width//2, h//2 + 50, button_width, button_height), "Back to Menu", self.font, BUTTON_COLOR, BUTTON_HOVER_COLOR),
        ]

    def load_sprites(self):
        self.player_sprite = pygame.Surface((44,44), pygame.SRCALPHA)
        pygame.draw.rect(self.player_sprite, (110, 210, 255), self.player_sprite.get_rect(), border_radius=10)

        self.enemy_sprites = []
        colors = [(255, 95, 98), (255, 165, 90), (150, 120, 255)]
        sizes = [40, 52, 64]
        for c, s in zip(colors, sizes):
            surf = pygame.Surface((s, s), pygame.SRCALPHA)
            pygame.draw.rect(surf, c, surf.get_rect(), border_radius=8)
            self.enemy_sprites.append(surf)

    def reset(self):
        self.player.pos = Vector2(WORLD_WIDTH*0.5, WORLD_HEIGHT*0.7)
        self.player.health = self.player.max_health
        self.player.score = 0
        self.bullets = []
        self.enemies = []
        self.particles = []
        self.spawn_timer = 0.5
        self.difficulty = 0.0
        self.enemies_killed = 0
        self.time = 0.0

    def save_player_progress(self):
        data = {
            "currency": self.player.currency,
            "weapons_owned": self.player.weapons_owned
        }
        self.save_manager.save_game(data)

    def spawn_enemy(self):
        screen_w, screen_h = self.screen.get_size()
        player_x, player_y = self.player.pos.x, self.player.pos.y

        spawn_dist_x = screen_w / 2 + 100
        spawn_dist_y = screen_h / 2 + 100

        edge = random.choice(['top','bottom','left','right'])

        if edge == 'top':
            pos_x = random.uniform(player_x - spawn_dist_x, player_x + spawn_dist_x)
            pos_y = player_y - spawn_dist_y
        elif edge == 'bottom':
            pos_x = random.uniform(player_x - spawn_dist_x, player_x + spawn_dist_x)
            pos_y = player_y + spawn_dist_y
        elif edge == 'left':
            pos_x = player_x - spawn_dist_x
            pos_y = random.uniform(player_y - spawn_dist_y, player_y + spawn_dist_y)
        else: # right
            pos_x = player_x + spawn_dist_x
            pos_y = random.uniform(player_y - spawn_dist_y, player_y + spawn_dist_y)

        pos_x = clamp(pos_x, 0, WORLD_WIDTH)
        pos_y = clamp(pos_y, 0, WORLD_HEIGHT)
        pos = (pos_x, pos_y)

        kind = random.choices([0,1,2], [0.6, 0.25, 0.15])[0]
        speed = random.uniform(60, 180)
        hp = 1 + kind
        sprite = self.enemy_sprites[kind]
        enemy = Enemy(pos, kind, speed, hp, sprite)
        self.enemies.append(enemy)

    def update_playing(self, dt):
        self.time += dt
        self.difficulty = min(1.5, self.difficulty + dt*0.1)
        self.spawn_timer -= dt
        if self.spawn_timer <= 0:
            self.spawn_timer = 0.9 * max(0.3, 1 - self.difficulty*0.8)
            self.spawn_enemy()

        keys = pygame.key.get_pressed()
        self.player.update(dt, keys)

        mouse_screen_pos = Vector2(pygame.mouse.get_pos())
        mouse_world_pos = mouse_screen_pos + self.camera
        mouse_pressed = pygame.mouse.get_pressed()
        if mouse_pressed[0] and self.player.can_fire():
            new_bullets = self.player.fire(mouse_world_pos)
            self.bullets.extend(new_bullets)
            self.shoot_sound.play()

        for bullet in self.bullets[:]:
            bullet.update(dt)
            if bullet.is_dead():
                self.bullets.remove(bullet)

        for enemy in self.enemies[:]:
            enemy.update(dt, self.player.pos)

            for bullet in self.bullets[:]:
                if (enemy.pos - bullet.pos).length_squared() < (enemy.radius + bullet.radius)**2:
                    enemy.hp -= bullet.damage
                    self.bullets.remove(bullet)
                    self.hit_sound.play()
                    for _ in range(6):
                        vel = Vector2(random.uniform(-150,150), random.uniform(-150,150))
                        p = Particle(enemy.pos, vel, random.randint(3,6), (255,255,255), 0.4)
                        self.particles.append(p)
                    if enemy.hp <= 0:
                        self.player.score += 10 + enemy.kind*5
                        self.player.currency += 5 + enemy.kind*5  # Reward currency
                        self.enemies_killed += 1
                        self.save_player_progress()
                        for _ in range(18):
                            vel = Vector2(random.uniform(-300,300), random.uniform(-300,300))
                            p = Particle(enemy.pos, vel, random.randint(6,12), (255,255,255), 0.8)
                            self.particles.append(p)
                        self.enemies.remove(enemy)
                        break

            if (enemy.pos - self.player.pos).length_squared() < (enemy.radius + self.player.size//2)**2:
                if self.player.damage_timer <= 0:
                    self.player.health -= 15
                    self.player.damage_timer = self.player.damage_cooldown
                    self.hit_sound.play()
                    for _ in range(20):
                        vel = Vector2(random.uniform(-350,350), random.uniform(-350,350))
                        p = Particle(self.player.pos, vel, random.randint(8,16), (255,80,80), 1.1)
                        self.particles.append(p)
                    if self.player.health <= 0:
                        self.state = STATE_GAMEOVER
                        self.save_player_progress()

        for p in self.particles[:]:
            p.update(dt)
            if p.is_dead():
                self.particles.remove(p)
    
    def handle_menu_events(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.main_menu_buttons[0].rect.collidepoint(event.pos):
                self.state = STATE_MODE_SELECT
            elif self.main_menu_buttons[1].rect.collidepoint(event.pos):
                self.state = STATE_SHOP
            elif self.main_menu_buttons[2].rect.collidepoint(event.pos):
                pygame.quit()
                sys.exit()

    def handle_mode_select_events(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.mode_select_buttons[0].rect.collidepoint(event.pos):
                self.state = STATE_PLAYING
                self.reset()
            elif self.mode_select_buttons[1].rect.collidepoint(event.pos):
                self.state = STATE_PLAYING
                self.reset()
                self.difficulty = -0.5 # Start "levels" mode easier
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.state = STATE_MENU

    def handle_shop_events(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.state = STATE_MENU
            return
        
        if event.type == pygame.MOUSEBUTTONDOWN:
            for button in self.shop_buttons:
                if button.rect.collidepoint(event.pos):
                    if button.text == "Back to Menu":
                        self.state = STATE_MENU
                        return
                    
                    weapon_name = button.text
                    if weapon_name in self.player.weapons_owned:
                        self.player.current_weapon_name = weapon_name
                        self.player.current_weapon = WEAPONS[weapon_name]
                        self.purchase_error_message = f"Equipped {weapon_name}!"
                        self.purchase_error_timer = 3.0
                    else:
                        weapon_data = WEAPONS[weapon_name]
                        if self.player.currency >= weapon_data["price"]:
                            self.player.currency -= weapon_data["price"]
                            self.player.weapons_owned.append(weapon_name)
                            self.player.current_weapon_name = weapon_name
                            self.player.current_weapon = WEAPONS[weapon_name]
                            self.purchase_error_message = f"Purchased and equipped {weapon_name}!"
                            self.purchase_error_timer = 3.0
                            self.save_player_progress()
                        else:
                            self.purchase_error_message = "Not enough currency!"
                            self.purchase_error_timer = 3.0

    def handle_game_over_events(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.game_over_buttons[0].rect.collidepoint(event.pos):
                self.state = STATE_MENU
                self.reset()
        if event.type == pygame.KEYDOWN:
            self.state = STATE_MENU
            self.reset()

    def draw_health_bar(self, surf, x, y, w, h, current, maximum):
        ratio = clamp01(current / maximum)
        pygame.draw.rect(surf, (70,70,70), (x,y,w,h), border_radius=4)
        pygame.draw.rect(surf, (240,60,60), (x,y,int(w*ratio),h), border_radius=4)

    def draw_grid(self):
        screen_w, screen_h = self.screen.get_size()
        cam_x, cam_y = self.camera.x, self.camera.y
        start_x = int(cam_x // CELL_SIZE) * CELL_SIZE
        start_y = int(cam_y // CELL_SIZE) * CELL_SIZE

        for x in range(start_x, int(cam_x + screen_w) + CELL_SIZE, CELL_SIZE):
            draw_pos_x = x - cam_x
            pygame.draw.line(self.screen, GRID_COLOR, (draw_pos_x, 0), (draw_pos_x, screen_h))

        for y in range(start_y, int(cam_y + screen_h) + CELL_SIZE, CELL_SIZE):
            draw_pos_y = y - cam_y
            pygame.draw.line(self.screen, GRID_COLOR, (0, draw_pos_y), (screen_w, draw_pos_y))

    def draw_playing(self):
        self.screen.fill(BG_COLOR)

        screen_w, screen_h = self.screen.get_size()
        self.camera.x += (self.player.pos.x - self.camera.x - screen_w / 2) * 0.1
        self.camera.y += (self.player.pos.y - self.camera.y - screen_h / 2) * 0.1
        self.camera.x = clamp(self.camera.x, 0, WORLD_WIDTH - screen_w)
        self.camera.y = clamp(self.camera.y, 0, WORLD_HEIGHT - screen_h)

        self.draw_grid()

        mouse_pos_vec = Vector2(pygame.mouse.get_pos())
        self.player.draw(self.screen, mouse_pos_vec, self.camera)
        for bullet in self.bullets:
            bullet.draw(self.screen, self.camera)
        for enemy in self.enemies:
            enemy.draw(self.screen, self.camera)
        for p in self.particles:
            p.draw(self.screen, self.camera)

        # UI Elements (drawn without camera offset)
        self.draw_health_bar(self.screen, 20, 20, 150, 20, self.player.health, self.player.max_health)

        score_text = self.font.render(f"Score: {self.player.score}", True, TEXT_COLOR)
        currency_text = self.font.render(f"Cash: {self.player.currency}", True, CURRENCY_COLOR)
        weapon_text = self.font.render(f"Weapon: {self.player.current_weapon_name}", True, TEXT_COLOR)
        level_text = self.font.render(f"Level: {self.enemies_killed // 10 + 1}", True, TEXT_COLOR)
        
        self.screen.blit(score_text, (screen_w - score_text.get_width() - 15, 20))
        self.screen.blit(currency_text, (screen_w - currency_text.get_width() - 15, 50))
        self.screen.blit(weapon_text, (screen_w - weapon_text.get_width() - 15, 80))
        self.screen.blit(level_text, (screen_w - level_text.get_width() - 15, 110))

        pygame.display.flip()

    def draw_game_over(self):
        w, h = self.screen.get_size()
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        go_text = self.big_font.render("GAME OVER", True, (255, 80, 80))
        score_text = self.font.render(f"Final Score: {self.player.score}", True, (255, 255, 255))
        
        go_rect = go_text.get_rect(center=(w//2, h//2 - 50))
        score_rect = score_text.get_rect(center=(w//2, h//2))
        
        self.screen.blit(go_text, go_rect)
        self.screen.blit(score_text, score_rect)
        
        mouse_pos = pygame.mouse.get_pos()
        for button in self.game_over_buttons:
            button.rect.center = (w//2, h//2 + 50)
            button.draw(self.screen, mouse_pos)
            
        pygame.display.flip()

    def draw_menu(self):
        self.screen.fill(BG_COLOR)
        w, h = self.screen.get_size()
        mouse_pos = pygame.mouse.get_pos()

        title_text = self.big_font.render("Modern Pygame Shooter", True, TEXT_COLOR)
        title_rect = title_text.get_rect(center=(w//2, h//2 - 150))
        self.screen.blit(title_text, title_rect)

        for button in self.main_menu_buttons:
            button.draw(self.screen, mouse_pos)

        pygame.display.flip()
        
    def draw_mode_select(self):
        self.screen.fill(BG_COLOR)
        w, h = self.screen.get_size()
        mouse_pos = pygame.mouse.get_pos()
        
        title_text = self.big_font.render("Select Mode", True, TEXT_COLOR)
        title_rect = title_text.get_rect(center=(w//2, h//2 - 150))
        self.screen.blit(title_text, title_rect)
        
        for button in self.mode_select_buttons:
            button.draw(self.screen, mouse_pos)
            
        pygame.display.flip()

    def draw_shop(self):
        self.screen.fill(BG_COLOR)
        w, h = self.screen.get_size()
        mouse_pos = pygame.mouse.get_pos()

        title_text = self.big_font.render("Weapon Shop", True, TEXT_COLOR)
        title_rect = title_text.get_rect(center=(w//2, 50))
        self.screen.blit(title_text, title_rect)

        currency_text = self.font.render(f"Your Cash: {self.player.currency}", True, CURRENCY_COLOR)
        currency_rect = currency_text.get_rect(center=(w//2, 120))
        self.screen.blit(currency_text, currency_rect)

        for button in self.shop_buttons:
            button.draw(self.screen, mouse_pos)
            
            # This check is to avoid drawing info for the "Back to Menu" button
            if button.text in WEAPONS:
                weapon_name = button.text
                weapon_data = WEAPONS[weapon_name]
                
                info_text_x = button.rect.left + 15
                info_y = button.rect.bottom + 5

                price_text = self.font.render(f"Price: {weapon_data['price']}", True, TEXT_COLOR)
                fire_rate_text = self.font.render(f"Fire Rate: {1/weapon_data['fire_rate']:.1f} RPS", True, INFO_COLOR)

                self.screen.blit(price_text, (info_text_x, info_y))
                self.screen.blit(fire_rate_text, (info_text_x, info_y + 25))

                status_text = ""
                status_color = TEXT_COLOR
                if weapon_name in self.player.weapons_owned:
                    status_text = "EQUIPPED" if self.player.current_weapon_name == weapon_name else "OWNED"
                    if self.player.current_weapon_name == weapon_name:
                        status_color = (110, 210, 255)

                status_surf = self.font.render(status_text, True, status_color)
                status_rect = status_surf.get_rect(right=button.rect.right - 10, centery=button.rect.centery)
                self.screen.blit(status_surf, status_rect)

        if self.purchase_error_timer > 0:
            error_surf = self.font.render(self.purchase_error_message, True, ERROR_COLOR)
            error_rect = error_surf.get_rect(center=(w // 2, h - 50))
            self.screen.blit(error_surf, error_rect)
            self.purchase_error_timer -= self.clock.get_time() / 1000

        pygame.display.flip()

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.VIDEORESIZE:
                    self.create_buttons()
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                    pygame.display.toggle_fullscreen()
                    pygame.event.post(pygame.event.Event(pygame.VIDEORESIZE, {}))
                
                if self.state == STATE_MENU:
                    self.handle_menu_events(event)
                elif self.state == STATE_MODE_SELECT:
                    self.handle_mode_select_events(event)
                elif self.state == STATE_GAMEOVER:
                    self.handle_game_over_events(event)
                elif self.state == STATE_SHOP:
                    self.handle_shop_events(event)

            if self.state == STATE_PLAYING:
                self.update_playing(dt)
                self.draw_playing()
            elif self.state == STATE_MENU:
                self.draw_menu()
            elif self.state == STATE_MODE_SELECT:
                self.draw_mode_select()
            elif self.state == STATE_SHOP:
                self.draw_shop()
            elif self.state == STATE_GAMEOVER:
                self.draw_game_over()

        pygame.quit()
        sys.exit()

def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption("Modern Pygame Shooter")
    game = Game(screen)
    game.run()

if __name__ == "__main__":
    main()
