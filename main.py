import pygame
import sys
import os
import math

pygame.init()
pygame.mixer.init()

# ── constants ──────────────────────────────────────────
WIDTH, HEIGHT = 800, 600
TILE = 32
FPS = 60

INK        = (10, 9, 7)
PAPER      = (242, 237, 230)
DIM        = (90, 80, 64)
GOLD       = (200, 169, 110)
ACCENT     = (184, 92, 48)
OVERLAP    = (74, 106, 90)
DARK_TILE  = (18, 16, 12)
MID_TILE   = (26, 22, 16)
WALL_COLOR = (38, 32, 22)

FONT_PATH  = None  # set to a .ttf path if you have one
FONT_SM    = pygame.font.SysFont("monospace", 11)
FONT_MD    = pygame.font.SysFont("monospace", 14)
FONT_LG    = pygame.font.SysFont("monospace", 18)
FONT_TITLE = pygame.font.SysFont("monospace", 28, bold=True)

screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("記憶地圖 — Memory Map")
clock = pygame.time.Clock()


# ── asset loader (graceful fallback) ──────────────────
def load_image(path, size=None):
    """Load image or return a colored placeholder rect surface."""
    if os.path.exists(path):
        img = pygame.image.load(path).convert_alpha()
        if size:
            img = pygame.transform.scale(img, size)
        return img
    # placeholder
    w, h = size if size else (64, 64)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    surf.fill((60, 50, 38))
    label = FONT_SM.render(os.path.basename(path), True, DIM)
    surf.blit(label, (4, h // 2 - 6))
    return surf

def load_sound(path):
    if os.path.exists(path):
        return pygame.mixer.Sound(path)
    return None


# ── dialog system ──────────────────────────────────────
class Dialog:
    def __init__(self):
        self.active   = False
        self.lines    = []
        self.index    = 0       # current line
        self.char_i   = 0       # typewriter char index
        self.timer    = 0
        self.speed    = 2       # chars per frame
        self.image    = None    # optional image to show
        self.tag      = ""
        self.done     = False

    def start(self, lines, tag="", image=None):
        self.lines  = lines
        self.index  = 0
        self.char_i = 0
        self.timer  = 0
        self.active = True
        self.done   = False
        self.tag    = tag
        self.image  = image

    def update(self):
        if not self.active or self.done:
            return
        self.timer += 1
        if self.timer % max(1, self.speed) == 0:
            current = self.lines[self.index]
            if self.char_i < len(current):
                self.char_i += 1

    def advance(self):
        """Call on SPACE / ENTER. Returns True when dialog closes."""
        current = self.lines[self.index]
        if self.char_i < len(current):
            self.char_i = len(current)   # skip to end
            return False
        self.index += 1
        if self.index >= len(self.lines):
            self.active = False
            self.done   = True
            return True
        self.char_i = 0
        return False

    def draw(self, surf):
        if not self.active:
            return

        # dim background
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        surf.blit(overlay, (0, 0))

        box_y  = HEIGHT - 220
        box_h  = 200
        box_x  = 40
        box_w  = WIDTH - 80

        # optional image panel on left
        img_w = 0
        if self.image:
            img_w = 160
            img_x = box_x + 16
            img_y = box_y + 20
            surf.blit(pygame.transform.scale(self.image, (img_w - 16, box_h - 40)), (img_x, img_y))

        # dialog box
        pygame.draw.rect(surf, (20, 18, 14), (box_x, box_y, box_w, box_h))
        pygame.draw.rect(surf, GOLD, (box_x, box_y, box_w, box_h), 1)

        # tag
        if self.tag:
            tag_surf = FONT_SM.render(self.tag.upper(), True, DIM)
            surf.blit(tag_surf, (box_x + img_w + 20, box_y + 12))
            pygame.draw.line(surf, WALL_COLOR,
                             (box_x + img_w + 20, box_y + 26),
                             (box_x + box_w - 20, box_y + 26), 1)

        # typewriter text — word wrap
        text_x   = box_x + img_w + 20
        text_y   = box_y + 36
        max_w    = box_w - img_w - 40
        current  = self.lines[self.index][:self.char_i]
        wrapped  = wrap_text(current, FONT_MD, max_w)
        for i, line in enumerate(wrapped):
            t = FONT_MD.render(line, True, PAPER)
            surf.blit(t, (text_x, text_y + i * 22))

        # continue prompt
        if self.char_i >= len(self.lines[self.index]):
            prompt = "▶ SPACE" if self.index < len(self.lines) - 1 else "▶ SPACE to close"
            p = FONT_SM.render(prompt, True, DIM)
            surf.blit(p, (box_x + box_w - p.get_width() - 16, box_y + box_h - 22))


def wrap_text(text, font, max_width):
    words  = text.split(" ")
    lines  = []
    line   = ""
    for word in words:
        test = line + (" " if line else "") + word
        if font.size(test)[0] <= max_width:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


# ── interactable object ────────────────────────────────
class Interactable:
    """A hotspot in a room. Player presses E near it to trigger dialog."""
    def __init__(self, x, y, w, h, lines, tag="", image=None,
                 color=GOLD, label="", sound=None):
        self.rect   = pygame.Rect(x, y, w, h)
        self.lines  = lines
        self.tag    = tag
        self.image  = image
        self.color  = color
        self.label  = label
        self.sound  = sound        # pygame.mixer.Sound or None
        self.pulse  = 0

    def update(self):
        self.pulse = (self.pulse + 2) % 360

    def draw(self, surf, cam_x, cam_y):
        rx = self.rect.x - cam_x
        ry = self.rect.y - cam_y
        alpha = int(140 + 60 * math.sin(math.radians(self.pulse)))
        s = pygame.Surface((self.rect.w, self.rect.h), pygame.SRCALPHA)
        s.fill((*self.color, alpha // 4))
        surf.blit(s, (rx, ry))
        pygame.draw.rect(surf, (*self.color, alpha), (rx, ry, self.rect.w, self.rect.h), 1)
        if self.label:
            lbl = FONT_SM.render(self.label, True, (*self.color, alpha))
            surf.blit(lbl, (rx + self.rect.w // 2 - lbl.get_width() // 2, ry - 16))

    def in_range(self, player_rect, distance=60):
        return self.rect.inflate(distance, distance).colliderect(player_rect)

    def trigger(self, dialog, sound_manager):
        if self.sound:
            sound_manager.play(self.sound)
        dialog.start(self.lines, self.tag, self.image)


# ── sound manager ──────────────────────────────────────
class SoundManager:
    def __init__(self):
        self.ambient = None

    def set_ambient(self, sound):
        if self.ambient:
            self.ambient.stop()
        self.ambient = sound
        if sound:
            sound.play(loops=-1)

    def play(self, sound):
        if sound:
            sound.play()

    def stop_ambient(self):
        if self.ambient:
            self.ambient.stop()
            self.ambient = None


# ── player ────────────────────────────────────────────
class Player:
    SIZE   = 12
    SPEED  = 3
    COLOR  = PAPER

    def __init__(self, x, y):
        self.rect     = pygame.Rect(x, y, self.SIZE, self.SIZE)
        self.vel      = [0, 0]
        self.facing   = "down"
        self.step     = 0
        self.step_t   = 0

    def handle_input(self, keys):
        self.vel = [0, 0]
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            self.vel[1] = -self.SPEED; self.facing = "up"
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            self.vel[1] =  self.SPEED; self.facing = "down"
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            self.vel[0] = -self.SPEED; self.facing = "left"
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            self.vel[0] =  self.SPEED; self.facing = "right"

    def move(self, walls):
        self.rect.x += self.vel[0]
        for w in walls:
            if self.rect.colliderect(w):
                if self.vel[0] > 0: self.rect.right  = w.left
                if self.vel[0] < 0: self.rect.left   = w.right
        self.rect.y += self.vel[1]
        for w in walls:
            if self.rect.colliderect(w):
                if self.vel[1] > 0: self.rect.bottom = w.top
                if self.vel[1] < 0: self.rect.top    = w.bottom

        if self.vel[0] != 0 or self.vel[1] != 0:
            self.step_t += 1
            if self.step_t % 16 == 0:
                self.step = (self.step + 1) % 4

    def draw(self, surf, cam_x, cam_y):
        rx = self.rect.x - cam_x
        ry = self.rect.y - cam_y
        # simple dot character with direction indicator
        pygame.draw.circle(surf, self.COLOR, (rx + self.SIZE//2, ry + self.SIZE//2), self.SIZE//2)
        # direction nub
        offsets = {"up":(0,-1),"down":(0,1),"left":(-1,0),"right":(1,0)}
        ox, oy  = offsets[self.facing]
        nx = rx + self.SIZE//2 + ox * (self.SIZE//2 + 3)
        ny = ry + self.SIZE//2 + oy * (self.SIZE//2 + 3)
        pygame.draw.circle(surf, GOLD, (nx, ny), 3)


# ── tilemap room ───────────────────────────────────────
class Room:
    """
    A room is a 2D grid of tile IDs.
    0 = floor, 1 = wall, 2 = dark floor accent

    tiles: list of strings, each char = one tile column-row
    exits: dict { direction: (target_room_id, spawn_x, spawn_y) }
    """
    TILE_COLORS = {
        "0": DARK_TILE,
        "2": MID_TILE,
        "1": WALL_COLOR,
    }

    def __init__(self, name, tag, tiles, interactables,
                 exits=None, ambient_sound=None, bg_color=INK):
        self.name          = name
        self.tag           = tag
        self.tiles         = tiles          # list of strings
        self.rows          = len(tiles)
        self.cols          = len(tiles[0]) if tiles else 0
        self.interactables = interactables
        self.exits         = exits or {}    # {"right": ("room_id", px, py)}
        self.ambient_sound = ambient_sound
        self.bg_color      = bg_color
        self.pixel_w       = self.cols * TILE
        self.pixel_h       = self.rows * TILE

    def get_walls(self):
        walls = []
        for r, row in enumerate(self.tiles):
            for c, ch in enumerate(row):
                if ch == "1":
                    walls.append(pygame.Rect(c * TILE, r * TILE, TILE, TILE))
        # boundary walls (invisible, keep player inside)
        walls.append(pygame.Rect(-TILE, 0, TILE, self.pixel_h))
        walls.append(pygame.Rect(self.pixel_w, 0, TILE, self.pixel_h))
        walls.append(pygame.Rect(0, -TILE, self.pixel_w, TILE))
        walls.append(pygame.Rect(0, self.pixel_h, self.pixel_w, TILE))
        return walls

    def draw_tiles(self, surf, cam_x, cam_y):
        for r, row in enumerate(self.tiles):
            for c, ch in enumerate(row):
                color = self.TILE_COLORS.get(ch, DARK_TILE)
                rx = c * TILE - cam_x
                ry = r * TILE - cam_y
                if -TILE < rx < WIDTH and -TILE < ry < HEIGHT:
                    pygame.draw.rect(surf, color, (rx, ry, TILE, TILE))
                    if ch != "1":
                        pygame.draw.rect(surf, (0,0,0,30), (rx, ry, TILE, TILE), 1)

    def draw_hud(self, surf):
        tag_surf = FONT_SM.render(self.tag.upper(), True, DIM)
        surf.blit(tag_surf, (16, 16))
        name_surf = FONT_MD.render(self.name, True, PAPER)
        surf.blit(name_surf, (16, 30))


# ── define rooms ───────────────────────────────────────
#
# Map layout (rooms):
#
#   [canton_kitchen] --right--> [overlap_table] --right--> [chicago_apt]
#                                     |
#                                   down
#                               [chinatown_street]
#
# Tiles: "1"=wall "0"=floor "2"=accent floor

def build_rooms(images):

    # ── room 1: canton kitchen ─────────────────────────
    canton_tiles = [
        "1111111111111111111111111",
        "1000000000000000000000001",
        "1020000000000000000000201",
        "1000000000000000000000001",
        "1000000000000000000000001",
        "1000000000000000000000001",
        "1020000000000000000000201",
        "1000000000000000000000001",
        "1000000000000000000000001",
        "1000000000000000000000001",
        "1020000000000000000000201",
        "1000000000000000000000001",
        "1000000000000000000000001",
        "1111111111110111111111111",  # gap at col 12 = exit right
    ]
    canton_objs = [
        Interactable(
            2*TILE, 2*TILE, 3*TILE, 3*TILE,
            lines=[
                "The clay pot sits on the stove.",
                "You can hear it before you can see it — a low bubbling, a slow exhale of steam.",
                "Your grandmother never used a timer. She knew by the smell when the crust had formed.",
                "煲仔飯. Clay pot rice. A dish that requires presence.",
            ],
            tag="Canton — 廣州",
            image=images.get("claypot"),
            color=GOLD,
            label="煲仔飯",
        ),
        Interactable(
            18*TILE, 5*TILE, 3*TILE, 3*TILE,
            lines=[
                "A stack of dim sum baskets.",
                "Sunday mornings. Ordering by pointing because the words escape you.",
                "The trolley wheels past before you can decide.",
                "飲茶. Drinking tea. But it was never just about the tea.",
            ],
            tag="Canton — 廣州",
            image=images.get("dimsum"),
            color=GOLD,
            label="飲茶",
        ),
        Interactable(
            10*TILE, 9*TILE, 4*TILE, 2*TILE,
            lines=[
                "A handwritten recipe card. The ink has faded.",
                "Some of the characters you can't read anymore.",
                "You're not sure if that's because of the fading, or because you've forgotten.",
            ],
            tag="Canton — 廣州",
            color=GOLD,
            label="食譜",
        ),
    ]

    # ── room 2: overlap table ──────────────────────────
    overlap_tiles = [
        "1111110111111111111111111",  # gap at col 6 = exit left
        "1000000000000000000000001",
        "1000000000000000000000001",
        "1020002000200020002000201",
        "1000000000000000000000001",
        "1000000000000000000000001",
        "1000000000000000000000001",
        "1020002000200020002000201",
        "1000000000000000000000001",
        "1000000000000000000000001",
        "1000000000000000000000001",
        "1020002000200020002000201",
        "1000000000000000000000001",
        "1111111111110111111111111",  # gap at col 12 = exit right + down
    ]
    overlap_objs = [
        Interactable(
            4*TILE, 4*TILE, 5*TILE, 5*TILE,
            lines=[
                "Roast pork. 叉燒.",
                "In Canton — a street stall. Newspaper wrapping. Eaten standing in the afternoon heat.",
                "In Chicago — a restaurant on Wentworth. Styrofoam tray. Fluorescent light.",
                "The same dish.",
                "Which one tastes more like home?",
            ],
            tag="Overlap — 重疊",
            image=images.get("pork"),
            color=OVERLAP,
            label="叉燒",
        ),
        Interactable(
            14*TILE, 4*TILE, 4*TILE, 4*TILE,
            lines=[
                "A white cardboard takeout box with a wire handle.",
                "It exists in both cities.",
                "Here — nostalgia.",
                "There — Tuesday.",
                "The same object. Entirely different weight.",
            ],
            tag="Overlap — 重疊",
            image=images.get("takeout"),
            color=OVERLAP,
            label="外賣盒",
        ),
        Interactable(
            10*TILE, 9*TILE, 5*TILE, 2*TILE,
            lines=[
                "Two sets of chopsticks. Two sets of everything.",
                "You've learned to keep two versions of yourself ready.",
                "It's not lying. It's translation.",
            ],
            tag="Overlap — 重疊",
            color=OVERLAP,
            label="筷子",
        ),
    ]

    # ── room 3: chicago apartment kitchen ──────────────
    chicago_tiles = [
        "1111110111111111111111111",  # gap = exit left
        "1000000000000000000000001",
        "1020000000000000000000001",
        "1000000000000000000000001",
        "1000000000000000000000001",
        "1000000000000000000000001",
        "1020000000000000000000001",
        "1000000000000000000000001",
        "1000000000000000000000001",
        "1000000000000000000000001",
        "1020000000000000000000001",
        "1000000000000000000000001",
        "1000000000000000000000001",
        "1111111111111111111111111",
    ]
    chicago_objs = [
        Interactable(
            2*TILE, 3*TILE, 4*TILE, 4*TILE,
            lines=[
                "Cooking alone.",
                "The same recipes, but the ingredients are slightly wrong.",
                "The ginger is drier. The soy sauce is sweeter.",
                "I improvise. I adapt.",
                "The dish becomes something new. I'm not sure that's loss.",
            ],
            tag="Chicago — 芝加哥",
            image=images.get("kitchen"),
            color=ACCENT,
            label="公寓廚房",
        ),
        Interactable(
            16*TILE, 5*TILE, 4*TILE, 3*TILE,
            lines=[
                "The window faces the L track.",
                "Every few minutes, a low rumble. Steel on steel.",
                "At first it kept me awake.",
                "Now when I go back to Canton, the silence keeps me awake instead.",
            ],
            tag="Chicago — 芝加哥",
            color=ACCENT,
            label="地鐵聲",
        ),
        Interactable(
            10*TILE, 8*TILE, 5*TILE, 3*TILE,
            lines=[
                "A shelf of familiar labels, slightly wrong.",
                "Brands that sound like home but aren't.",
                "You learn to read the differences.",
                "Eventually you stop noticing. That's the part that scares you.",
            ],
            tag="Chicago — 芝加哥",
            image=images.get("packaging"),
            color=ACCENT,
            label="食品包裝",
        ),
    ]

    # ── room 4: chinatown street ───────────────────────
    street_tiles = [
        "1111110111111111111111111",  # gap = exit up
        "1000000000000000000000001",
        "1020000020000000200000201",
        "1000000000000000000000001",
        "1000000000000000000000001",
        "1000000000000000000000001",
        "1020000020000000200000201",
        "1000000000000000000000001",
        "1000000000000000000000001",
        "1000000000000000000000001",
        "1020000020000000200000201",
        "1000000000000000000000001",
        "1000000000000000000000001",
        "1111111111111111111111111",
    ]
    street_objs = [
        Interactable(
            3*TILE, 3*TILE, 5*TILE, 4*TILE,
            lines=[
                "Wentworth Avenue, Chicago.",
                "Familiar signs in an unfamiliar city.",
                "The feeling of recognition that isn't quite arrival.",
                "A neighbourhood performing a version of somewhere you're from.",
                "Close enough to feel. Far enough to ache.",
            ],
            tag="Chicago — 芝加哥",
            image=images.get("chinatown"),
            color=ACCENT,
            label="文華街",
        ),
        Interactable(
            14*TILE, 4*TILE, 5*TILE, 4*TILE,
            lines=[
                "A vendor calls out in Cantonese.",
                "Your body responds before your brain does.",
                "You turn. She's not talking to you.",
                "But for a moment — you were home.",
            ],
            tag="Chicago — 芝加哥",
            color=ACCENT,
            label="廣東話",
        ),
    ]

    rooms = {
        "canton": Room(
            name="Canton Kitchen",
            tag="Canton — 廣州",
            tiles=canton_tiles,
            interactables=canton_objs,
            exits={"right": ("overlap", 1*TILE, 7*TILE)},
        ),
        "overlap": Room(
            name="The Table Between",
            tag="Overlap — 重疊",
            tiles=overlap_tiles,
            interactables=overlap_objs,
            exits={
                "left":  ("canton",   22*TILE, 7*TILE),
                "right": ("chicago",  1*TILE,  7*TILE),
                "down":  ("street",   6*TILE,  1*TILE),
            },
        ),
        "chicago": Room(
            name="Chicago Apartment",
            tag="Chicago — 芝加哥",
            tiles=chicago_tiles,
            interactables=chicago_objs,
            exits={"left": ("overlap", 22*TILE, 7*TILE)},
        ),
        "street": Room(
            name="Chinatown, Wentworth Ave",
            tag="Chicago — 芝加哥",
            tiles=street_tiles,
            interactables=street_objs,
            exits={"up": ("overlap", 6*TILE, 11*TILE)},
        ),
    }
    return rooms


# ── camera ─────────────────────────────────────────────
def get_camera(player, room):
    cx = player.rect.centerx - WIDTH  // 2
    cy = player.rect.centery - HEIGHT // 2
    cx = max(0, min(cx, room.pixel_w - WIDTH))
    cy = max(0, min(cy, room.pixel_h - HEIGHT))
    return cx, cy


# ── title screen ───────────────────────────────────────
def title_screen():
    alpha = 0
    fade_in = True
    t = 0
    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return
        screen.fill(INK)

        t += 1
        if fade_in and alpha < 255:
            alpha = min(255, alpha + 2)

        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)

        # large chinese title
        zh = pygame.font.SysFont("monospace", 52, bold=False).render("記憶地圖", True, GOLD)
        overlay.blit(zh, (WIDTH//2 - zh.get_width()//2, HEIGHT//2 - 80))

        en = FONT_LG.render("memory map", True, DIM)
        overlay.blit(en, (WIDTH//2 - en.get_width()//2, HEIGHT//2 - 10))

        sub = FONT_SM.render("canton  /  chicago", True, (70, 62, 50))
        overlay.blit(sub, (WIDTH//2 - sub.get_width()//2, HEIGHT//2 + 20))

        blink = FONT_SM.render("press SPACE to enter", True,
                               PAPER if (t // 30) % 2 == 0 else DIM)
        overlay.blit(blink, (WIDTH//2 - blink.get_width()//2, HEIGHT//2 + 80))

        controls = [
            "WASD / arrows — move",
            "E — interact with objects",
            "SPACE — advance dialog",
        ]
        for i, c in enumerate(controls):
            cs = FONT_SM.render(c, True, (50, 44, 34))
            overlay.blit(cs, (WIDTH//2 - cs.get_width()//2, HEIGHT - 80 + i * 18))

        overlay.set_alpha(alpha)
        screen.blit(overlay, (0, 0))
        pygame.display.flip()
        clock.tick(FPS)


# ── main game loop ─────────────────────────────────────
def main():
    title_screen()

    # load images — put your actual files in an assets/ folder
    # filenames are just examples; rename to match yours
    images = {
        "claypot":   load_image("assets/claypot.png",   (160, 160)),
        "dimsum":    load_image("assets/dimsum.png",     (160, 160)),
        "pork":      load_image("assets/pork.png",       (160, 160)),
        "takeout":   load_image("assets/takeout.png",    (160, 160)),
        "kitchen":   load_image("assets/kitchen.png",    (160, 160)),
        "packaging": load_image("assets/packaging.png",  (160, 160)),
        "chinatown": load_image("assets/chinatown.png",  (160, 160)),
    }

    rooms   = build_rooms(images)
    sound_m = SoundManager()
    dialog  = Dialog()
    player  = Player(4 * TILE, 6 * TILE)

    current_room_id = "canton"
    current_room    = rooms[current_room_id]
    walls           = current_room.get_walls()

    def switch_room(room_id, px, py):
        nonlocal current_room_id, current_room, walls
        current_room_id = room_id
        current_room    = rooms[room_id]
        walls           = current_room.get_walls()
        player.rect.x   = px
        player.rect.y   = py
        sound_m.set_ambient(current_room.ambient_sound)

    hint_timer = 0

    while True:
        dt = clock.tick(FPS)

        # ── events ──
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()

                if dialog.active:
                    if ev.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_e):
                        dialog.advance()
                else:
                    # interact
                    if ev.key == pygame.K_e:
                        for obj in current_room.interactables:
                            if obj.in_range(player.rect):
                                obj.trigger(dialog, sound_m)
                                break

        # ── update ──
        if not dialog.active:
            keys = pygame.key.get_pressed()
            player.handle_input(keys)
            player.move(walls)

            # exit detection
            pr = player.rect
            rw = current_room.pixel_w
            rh = current_room.pixel_h
            exits = current_room.exits

            if pr.right >= rw - TILE and "right" in exits:
                rid, px, py = exits["right"]
                switch_room(rid, px, py)
            elif pr.left <= TILE and "left" in exits:
                rid, px, py = exits["left"]
                switch_room(rid, px, py)
            elif pr.bottom >= rh - TILE and "down" in exits:
                rid, px, py = exits["down"]
                switch_room(rid, px, py)
            elif pr.top <= TILE and "up" in exits:
                rid, px, py = exits["up"]
                switch_room(rid, px, py)

        dialog.update()
        for obj in current_room.interactables:
            obj.update()
        hint_timer += 1

        # ── draw ──
        screen.fill(current_room.bg_color)
        cam_x, cam_y = get_camera(player, current_room)

        current_room.draw_tiles(screen, cam_x, cam_y)

        for obj in current_room.interactables:
            obj.draw(screen, cam_x, cam_y)

        player.draw(screen, cam_x, cam_y)

        # proximity hint
        if not dialog.active:
            for obj in current_room.interactables:
                if obj.in_range(player.rect, 48):
                    hint = FONT_SM.render("E — examine", True, DIM)
                    screen.blit(hint, (WIDTH//2 - hint.get_width()//2, HEIGHT - 40))
                    break

        # room HUD
        current_room.draw_hud(screen)

        # minimap (top right, simple dots)
        draw_minimap(screen, rooms, current_room_id)

        dialog.draw(screen)

        pygame.display.flip()


def draw_minimap(surf, rooms, current_id):
    """Simple dot minimap showing room connections."""
    positions = {
        "canton":  (WIDTH - 90, 18),
        "overlap": (WIDTH - 60, 18),
        "chicago": (WIDTH - 30, 18),
        "street":  (WIDTH - 60, 34),
    }
    for rid, (rx, ry) in positions.items():
        color = GOLD if rid == current_id else (40, 36, 28)
        pygame.draw.circle(surf, color, (rx, ry), 5)
        if rid == current_id:
            pygame.draw.circle(surf, GOLD, (rx, ry), 7, 1)
    # lines between connected rooms
    edges = [("canton","overlap"),("overlap","chicago"),("overlap","street")]
    for a, b in edges:
        ax, ay = positions[a]
        bx, by = positions[b]
        pygame.draw.line(surf, (40, 36, 28), (ax, ay), (bx, by), 1)


if __name__ == "__main__":
    main()
