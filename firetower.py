from __future__ import annotations
import random
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import List, Union, Callable, Set, Any, Optional, Dict, NamedTuple, Tuple

import PySimpleGUI as sg
from frozendict import frozendict


class classproperty:
    """
    a descriptor that creates a property on a class
    usage:
    class A:
        @U.classproperty
        def jeb(cls):
            return 2 * 3
    print(A.jeb)
    """

    def __init__(self, f):
        self.f = f

    # noinspection PyUnusedLocal
    def __get__(self, instance, cls):
        return self.f(cls)


class Point(NamedTuple):
    x: int
    y: int

    def __add__(self, o) -> Point:
        return Point(self.x + o.x, self.y + o.y)

    def __sub__(self, o) -> Point:
        return Point(self.x - o.x, self.y - o.y)

    @property
    def left(self) -> Point:
        return self + Point(-1, 0)

    @property
    def right(self) -> Point:
        return self + Point(1, 0)

    @property
    def up(self) -> Point:
        return self + Point(0, -1)

    @property
    def down(self) -> Point:
        return self + Point(0, 1)


class WindDir(Enum):
    N = 'north'
    W = 'west'
    E = 'east'
    S = 'south'

    def as_vector(self):
        return {
            WindDir.N: Point(0, -1),
            WindDir.W: Point(-1, 0),
            WindDir.E: Point(1, 0),
            WindDir.S: Point(0, 1)
        }.get(self)


class Corner:
    def __init__(self, y_wind: WindDir, x_wind: WindDir):
        if x_wind not in {WindDir.W, WindDir.E}:
            raise ValueError(f'{x_wind} is not a horizontal wind direction')
        if y_wind not in {WindDir.N, WindDir.S}:
            raise ValueError(f'{y_wind} is not a vertical wind direction')
        self.x_wind = x_wind
        self.y_wind = y_wind

    @property
    def point(self) -> Point:
        x = 0 if self.x_wind is WindDir.W else FireTowerGame.BOARD_SIZE - 1
        y = 0 if self.y_wind is WindDir.N else FireTowerGame.BOARD_SIZE - 1
        return Point(x, y)

    @property
    def tower(self) -> Set[Point]:
        x_range = range(0, 3) if self.x_wind is WindDir.W else range(FireTowerGame.BOARD_SIZE - 3,
                                                                     FireTowerGame.BOARD_SIZE)
        y_range = range(0, 3) if self.y_wind is WindDir.N else range(FireTowerGame.BOARD_SIZE - 3,
                                                                     FireTowerGame.BOARD_SIZE)
        return FireTowerGame.get_board_range(x_range, y_range)

    def __iter__(self):
        return iter([self.y_wind, self.x_wind])

    def __len__(self):
        return len([self.y_wind, self.x_wind])

    def __eq__(self, o):
        return self.x_wind is o.x_wind and self.y_wind is o.y_wind

    def __hash__(self):
        return hash((self.x_wind, self.y_wind))


CORNERS = [Corner(WindDir.N, WindDir.W), Corner(WindDir.N, WindDir.E), Corner(WindDir.S, WindDir.E),
           Corner(WindDir.S, WindDir.W)]


@dataclass
class Player:
    name: str
    corner: Corner
    active: bool = True

    @property
    def point(self):
        return self.corner.point

    @property
    def tower(self):
        return self.corner.tower


@dataclass
class Players:
    p1: Player
    p2: Player
    p3: Optional[Player] = None
    p4: Optional[Player] = None

    def __iter__(self):
        return iter([p for p in [self.p1, self.p2, self.p3, self.p4] if p is not None])

    @classmethod
    def get_players(cls, players: List[Optional[Player]]):
        """Given a list of players in slots, fill in empty slots with default values and return the list of players"""
        corners = {*CORNERS}
        taken_corners = {p.corner for p in players if p is not None}
        corners = deque(corners - taken_corners)
        return [p or Player(f'Player {i + 1}', corners.popleft()) for i, p in enumerate(players)]

    @classmethod
    def four_player(cls, *, p1: Optional[Player] = None, p2: Optional[Player] = None,
                    p3: Optional[Player] = None, p4: Optional[Player] = None):
        """construct a four-player set of players"""
        return cls(*cls.get_players([p1, p2, p3, p4]))

    @classmethod
    def three_player(cls, *, p1: Optional[Player] = None, p2: Optional[Player] = None, p3: Optional[Player] = None):
        """construct a three-player set of players"""
        return cls(*cls.get_players([p1, p2, p3]))

    @classmethod
    def two_player(cls, *, p1: Optional[Player] = None, p2: Optional[Player] = None):
        """construct a two-player set of players"""
        return cls(*cls.get_players([p1, p2]))


class TileStatus(Enum):
    fire = 'fire'
    tree = 'tree'
    firebreak = 'firebreak'
    off_board = 'off board'


class OrientationEnum(Enum):
    h = 'horizontal'
    v = 'vertical'

    @property
    def flip(self) -> OrientationEnum:
        if self is OrientationEnum.h:
            return OrientationEnum.v
        if self is OrientationEnum.v:
            return OrientationEnum.h


class FireTowerGame:
    BOARD_SIZE = 16

    @staticmethod
    def get_board_range(x_range: range, y_range: range) -> Set[Point]:
        return {Point(int(x), int(y)) for x in x_range for y in y_range}

    @classproperty
    def eternal_flame(cls) -> Set[Point]:
        return cls.get_board_range(x_range=range(int(cls.BOARD_SIZE / 2 - 1), int(cls.BOARD_SIZE / 2 + 1)),
                                   y_range=range(int(cls.BOARD_SIZE / 2 - 1), int(cls.BOARD_SIZE / 2 + 1)))

    def __init__(self):
        self.active = True
        self.board = Board({Point(r, c): TileStatus.tree for r in range(0, self.BOARD_SIZE)
                            for c in range(0, self.BOARD_SIZE)})

        for pos in self.eternal_flame:
            self.board[pos] = TileStatus.fire

        self.players = Players.four_player()

        self.wind = None
        self.action = self.add_wind_fire
        self.orientation = OrientationEnum.h
        self.roll_wind()

        self.window = sg.Window('FireTower', layout=self._init_layout())
        self.game_loop()

    def game_loop(self):
        while self.active:
            event, values = self.window.read()
            if event in (None, 'Cancel', 'Exit'):
                self.active = False
                self.window.close()
            self.update(event=event, values=values)
            self.draw()

    def set_oriented_action(self, action: Callable):
        if self.action == action:
            self.orientation = self.orientation.flip
        self.action = action

    def update(self, event: Optional[Any] = None, values: Optional[Union[Dict, List]] = None):
        if isinstance(event, Point):
            self.action(event)
        elif event == '-W-':
            self.roll_wind()
            self.window['wind'].update(f'Wind Direction: {self.wind.value}')
        elif event == '-Fire-':
            self.action = self.add_wind_fire
        elif event == '-DL-':
            self.set_oriented_action(self.dozer_line)
        elif event == '-SL-':
            self.set_oriented_action(self.scratch_line)
        elif event == '-DRF-':
            self.action = self.de_re_forest
        elif event == '-FL-':
            self.set_oriented_action(self.flare_up)
        elif event == '-EXPL-':
            self.action = self.explosion
        elif event == '-EMBR-':
            self.action = self.ember_phase_one
        elif event == '-BSNG-':
            self.action = self.burning_snag

        self.check_for_victory()

    def check_for_victory(self):
        current_remaining = [p for p in self.players if p.active]
        for p in current_remaining:
            if self.board[p.point] is TileStatus.fire:
                p.active = False
                for t_point in p.tower:
                    self.board[t_point] = TileStatus.fire
        new_remaining = [p for p in self.players if p.active]
        if len(new_remaining) == 1:
            self.victory(new_remaining[0])

    @property
    def towers(self) -> Set[Point]:
        return set.union(*[player.corner.tower for player in self.players])

    @property
    def corners(self) -> Set[Point]:
        return set.union(*[player.corner.point for player in self.players])

    def victory(self, player: Player):
        self.active = False
        print(f'{player.name} wins!')
        self.window.close()

    def roll_wind(self) -> WindDir:
        old_wind = self.wind
        valid_winds = {w for c in [p.corner for p in self.players if p.active] for w in c}
        print(f'Valid Winds: {valid_winds}')
        while self.wind is old_wind:
            self.wind = random.choice(list(valid_winds))
        return self.wind

    def _init_layout(self) -> List[List[Any]]:
        def action_btn(name: str):
            return sg.Button(name, size=(4, 1), button_color=('black', 'gray'), key=f'-{name}-')

        colors = self.board.get_colors(self.players)
        layout = [[sg.Button('', size=(2, 1), button_color=('white', colors[Point(r, c)]), key=Point(r, c))
                   for r in range(0, self.BOARD_SIZE)] for c in range(0, self.BOARD_SIZE)]
        layout.append([sg.Text(f'Wind Direction: {self.wind.value}', key='wind'), sg.Button('Wind', size=(4, 1),
                                                                                            button_color=(
                                                                                                'black', 'gray'),
                                                                                            key='-W-')])
        layout.append([action_btn('Fire'),
                       action_btn('DL'),
                       action_btn('SL'),
                       action_btn('DRF'),
                       action_btn('FL'),
                       action_btn('EXPL'),
                       action_btn('EMBR'),
                       action_btn('BSNG')])
        return layout

    def add_wind_fire(self, point: Point):
        wind_point = point - self.wind.as_vector()
        if self.board[point] is TileStatus.tree and self.board[wind_point] is TileStatus.fire:
            self.board[point] = TileStatus.fire

    def has_orthogonal(self, point: Point, status: TileStatus):
        return (self.board[point.left] is status or self.board[point.right] is status
                or self.board[point.up] is status or self.board[point.down] is status)

    def validate_firebreak(self, point: Point):
        return (self.board[point] is TileStatus.tree and point not in self.towers
                and not self.has_orthogonal(point, TileStatus.firebreak))

    def add_firebreak_cluster(self, cluster: Tuple[Point, Point]):
        valid = all([self.validate_firebreak(p) for p in cluster])
        if valid:
            for p in cluster:
                self.board[p] = TileStatus.firebreak
        else:
            print(f'{cluster} not valid for placing a firebreak')

    def dozer_line(self, point: Point):
        """Place two firebreak tokens adjacent to each other. Neither may be adjacent to any other firebreak"""
        cluster = (point, point.right) if self.orientation is OrientationEnum.h else (point, point.down)
        self.add_firebreak_cluster(cluster)

    def de_re_forest(self, point: Point):
        """Add or remove one firebreak token"""
        if self.validate_firebreak(point):
            self.board[point] = TileStatus.firebreak
        elif self.board[point] is TileStatus.firebreak:
            self.board[point] = TileStatus.tree
        else:
            print(f'Cannot add or remove firebreak at {point}')

    def scratch_line(self, point: Point):
        """Place two firebreak tokens one space apart, either horizontally or vertically"""
        cluster = (point, point.right.right) if self.orientation is OrientationEnum.h else (point, point.down.down)
        self.add_firebreak_cluster(cluster)

    def flare_up(self, point: Point):
        """
        Place three fire gems in a horizontal or vertical line.
        At least one gem must be orthogonal to an existing gem
        """
        flare_line = ([point, point.right, point.right.right] if self.orientation is OrientationEnum.h
                      else [point, point.down, point.down.down])
        filtered_flare = []
        for p in flare_line:
            if self.board[p] is TileStatus.firebreak:
                break
            if self.board[p] is TileStatus.tree:
                filtered_flare.append(p)
        if any(self.has_orthogonal(p, TileStatus.fire) for p in filtered_flare):
            for p in filtered_flare:
                self.board[p] = TileStatus.fire

    def burning_snag(self, point: Point):
        """Place four fire gems in a square pattern. The selected point is the upper-left corner of the square"""
        square = (point, point.right, point.down, point.right.down)
        if (any(self.has_orthogonal(p, TileStatus.fire) for p in square) and
                any(self.board[p] is TileStatus.tree for p in square)):
            for p in square:
                if self.board[p] is TileStatus.tree:
                    self.board[p] = TileStatus.fire

    def explosion(self, point: Point):
        """Convert an existing fire gem to a firebreak. All 8 surrounding tiles become fire if possible"""
        if self.board[point] is not TileStatus.fire or point in self.eternal_flame:
            return
        area = (point.up.left, point.up, point.up.right, point.right, point.left, point.down.left, point.down,
                point.down.right)
        if any(self.board[p] is TileStatus.tree for p in area):
            self.board[point] = TileStatus.firebreak
            for p in area:
                if self.board[p] is TileStatus.tree:
                    self.board[p] = TileStatus.fire

    def ember_phase_one(self, point: Point):
        """Select any fire gem on the board and remove it, then proceed to phase two"""
        if self.board[point] is TileStatus.fire and point not in self.eternal_flame and point not in self.towers:
            self.board[point] = TileStatus.tree
            self.action = self.ember_phase_two

    def ember_phase_two(self, point: Point):
        """Place the removed fire gem from phase one on any space that's orthogonal to an existing fire gem"""
        if self.board[point] is TileStatus.tree and self.has_orthogonal(point, TileStatus.fire):
            self.board[point] = TileStatus.fire
            self.action = self.no_action

    def no_action(self, *_, **__):
        pass

    def draw(self):
        self.board.draw(self.window, self.players)


class Board:
    CHAR_MAP = frozendict({
        TileStatus.fire: '*',
        TileStatus.tree: '^',
        TileStatus.firebreak: 'o'
    })
    COLOR_MAP = frozendict({
        TileStatus.fire: 'orange',
        TileStatus.tree: 'green',
        TileStatus.firebreak: 'purple'
    })

    def __init__(self, grid: Dict[Point, TileStatus]):
        self.grid = grid

    @staticmethod
    def on_board(point: Point) -> bool:
        return point.x in range(0, FireTowerGame.BOARD_SIZE) and point.y in range(0, FireTowerGame.BOARD_SIZE)

    def get_colors(self, players: Players) -> Dict[Point, str]:
        res = {point: self.COLOR_MAP[self[point]] for point in [Point(r, c)
                                                                for r in range(0, FireTowerGame.BOARD_SIZE)
                                                                for c in range(0, FireTowerGame.BOARD_SIZE)]}
        for p in players:
            for t_point in p.tower:
                res[t_point] = 'brown' if self[t_point] is TileStatus.tree else res[t_point]
            res[p.point] = 'white' if self[p.point] is TileStatus.tree else res[p.point]
        return res

    def draw(self, window: sg.Window, players: Players):
        colors = self.get_colors(players)
        for point in colors:
            window[point].update(button_color=('white', colors[point]))

    def __getitem__(self, pos: Point):
        if not isinstance(pos, Point):
            raise TypeError(f'Received {type(pos)}, expecting Point')
        if self.on_board(pos):
            return self.grid[pos]
        return TileStatus.off_board

    def __setitem__(self, pos: Point, value: TileStatus):
        if not isinstance(pos, Point):
            raise TypeError(f'Board setitem operation expects a Point, received {type(pos)} instead')
        if self.on_board(pos):
            self.grid[pos] = value
        return


class CardTypeEnum(Enum):
    water = 'water'
    fire = 'fire'
    wind = 'wind'
    firebreak = 'firebreak'
    special = 'special'


class Card:
    """A class describing a card in the deck of Fire Tower cards"""

    def __init__(self, name: str, description: str, card_type: CardTypeEnum, art_path: str, action: Callable):
        self.name = name
        self.description = description
        self.card_type = card_type
        self.art_path = art_path
        self.action = action

    def play(self):
        print(f'{self.name}: {self.description}')
        self.action()


game = FireTowerGame()
