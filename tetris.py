from piece import Piece
from copy import deepcopy
from i18n import t

# Optionale Solver-Telemetrie. debuglog ist stdlib-only, aber wir machen den
# Import bewusst weich: tetris.py muss auch ohne debuglog importierbar bleiben
# (z.B. in isolierten Unit-Tests), darum faellt es auf einen No-Op zurueck.
try:
    from debuglog import log
except Exception:  # pragma: no cover - nur Fallback, falls Modul fehlt
    class _NullLog:
        def event(self, *a, **k):
            pass

        def snapshot(self, *a, **k):
            pass

        def warning(self, *a, **k):
            pass

        def error(self, *a, **k):
            pass

    log = _NullLog()


class Tetris:

    board = None

    first = 0
    second = 0

    def __init__(self):
        self.board = [[0, 0, 0, 0, 0, 0],
                      [0, 0, 0, 0, 0, 0],
                      [0, 0, 0, 0, 0, 0],
                      [0, 0, 0, 0, 0, 0]]


    def find_first(self, piece, dictdump):
        # Ungueltiger Stein (Typ 0 / None) -> KEIN dict-Zugriff mit '0'.
        # Frueher warf dictdump['first']['0'] hier einen KeyError "'0'" und
        # liess den Puzzle-Bot still abbrechen.
        if piece is None or not piece.is_valid:
            log.event('find_first', t('tetris.invalid_piece_no_opening_book'))
            return 2, None

        # Kein/kaputtes Eroeffnungsbuch -> defensiv behandeln statt zu crashen.
        if not dictdump:
            return 2, None

        if not self.first:
            # .get()-Kette: fehlende/teil-korrupte Buch-Eintraege liefern None
            # statt KeyError (ein unvollstaendiges pieces_second.json konnte
            # hier sonst crashen, sobald das Buch wieder aktiv ist).
            entry = dictdump.get('first', {}).get(str(piece.piece_type)) or {}
            pos = entry.get('pos')
            if pos:
                self.first = piece.piece_type
                return 1, pos
            else:
                return 2, None
        if not self.second:
            first_entry = dictdump.get('first', {}).get(str(self.first)) or {}
            second_entry = first_entry.get('second', {}).get(str(piece.piece_type)) or {}
            pos = second_entry.get('pos')
            if pos:
                self.second = piece.piece_type
                return 1, pos
            else:
                return 2, None

        return 3, None

    def count_zeros(self):
        # Zaehlt die tatsaechlich leeren (0er-)Zellen im 4x6-Board.
        # Frueher iterierte die innere Schleife faelschlich ueber self.board
        # statt ueber die Zellen -> Ergebnis war konstant 8.
        return sum(1 for row in self.board for cell in row if cell == 0)

    def is_opening_position(self):
        # True, wenn das Brett komplett leer ist -> Eroeffnungsbuch-Startzustand.
        # Ein 4x6-Brett hat 24 Zellen; 'alle leer' aktiviert das Buch in
        # puzzle.set_puzzle_state (FIX Blocker A: dort war die Bedingung
        # invertiert). Board-Groesse wird generisch aus self.board bestimmt.
        if not self.board:
            return False
        total_cells = sum(len(row) for row in self.board)
        return self.count_zeros() == total_cells

    def verify_end(self):

        for i in self.board:
            if 0 in i:
                return False

        return True

    def insert_piece(self, position_x, position_y, piece):

        # Ungueltiger Stein -> nichts einsetzen (kein Zugriff auf form/height).
        if piece is None or not piece.is_valid:
            return False

        if (piece.height - 1 + position_x) > 3:
            return False
        elif (piece.width - 1 + position_y) > 5:
            return False

        pos_row = position_x
        pos_column = position_y

        for row in piece.form:
            for cel in row:
                if cel and self.board[pos_row][pos_column]:
                    return False
                self.board[pos_row][pos_column] += cel
                pos_column += 1
            pos_row += 1
            pos_column = position_y

        return True

    def verify_insert_piece(self, position_x, position_y, piece, board):

        # Ungueltiger Stein -> keine gueltige Platzierung.
        if piece is None or not piece.is_valid:
            return False

        if (piece.height - 1 + position_x) > 3:
            return False
        elif (piece.width - 1 + position_y) > 5:
            return False

        pos_row = position_x
        pos_column = position_y

        for row in piece.form:
            for cel in row:
                if cel and board[pos_row][pos_column]:
                    return False
                pos_column += 1
            pos_row += 1
            pos_column = position_y

        return True

    def verify_isolated(self, x, y):

        if (x == 0 and y == 0) or (x == 2 and y == 0):
            return self.board[x][y+1] == 1 and self.board[x+1][y] == 1

        if (x == 0 and y == 5) or (x == 2 and y == 5):
            return self.board[x][y-1] == 1 and self.board[x+1][y] == 1

        if (x == 1 and y == 0) or (x == 3 and y == 0):
            return self.board[x-1][y] == 1 and self.board[x][y+1] == 1

        if (x == 1 and y == 5) or (x == 3 and y == 5):
            return self.board[x-1][y] == 1 and self.board[x][y-1] == 1

        if (x == 0 or x == 2) and (y > 0 and y < 5):
            return (self.board[x][y-1] == 1 and self.board[x][y+1] == 1
                    and self.board[x+1][y] == 1)

        if (x == 1 or x == 3) and (y > 0 and y < 5):
            return (self.board[x][y-1] == 1 and self.board[x][y+1] == 1
                    and self.board[x-1][y] == 1)

        # Vorsichtsmassnahme: falls keine Bedingung greift, explizit False.
        return False

    def choose_better(self, piece, possibilites):

        # Ungueltiger Stein oder keine Moeglichkeiten -> nichts zu waehlen.
        if piece is None or not piece.is_valid or not possibilites:
            return None

        better_one = None
        better_total = -1

        for p in possibilites:
            tetris = Tetris()
            a = self.board
            tetris.board = [[a[x][y] for y in range(len(a[0]))] for x in range(len(a))]
            tetris.insert_piece(p[0], p[1], piece)

            pices_count = 0

            for i in range(1,7):
                if i != piece.piece_type:
                    possis = tetris.find_possibles(Piece(i))

                    pices_count += len(possis)

            if pices_count > better_total:
                better_total = pices_count
                better_one = p

        return better_one

    def find_possibles(self, piece):

        # Ungueltiger Stein -> keine Platzierungen, frueh raus (vor jeder Iteration).
        if piece is None or not piece.is_valid:
            return []

        # Tiefe Kopie des Boards: verify_insert_piece liest nur, aber die tiefe
        # Kopie macht die Invariante explizit und schuetzt vor kuenftigen Bugs.
        new_list = deepcopy(self.board)
        possibilites = []

        for i in range(0,4):
            for l in range(0,6):
                if self.verify_insert_piece(i, l, piece, new_list):
                    possibilites.append([i,l])

        ## Some strategies

        if piece.piece_type == 2:
            aux = [[0,5],[1,0]]
            return [i for i in possibilites if i in aux]
        if piece.piece_type == 6:
            aux = [[0,0],[0,1],[0,2],[0,3],[0,4],[0,5],
                   [2,1],[2,2],[2,3],[2,4],[2,5]]
            return [i for i in possibilites if i in aux]
        if piece.piece_type in [3,4,5]:
            aux = [[0,0],[0,1],[0,2],[0,3],[0,4],[0,5],
                   [2,0],[2,1],[2,2],[2,3],[2,4],[2,5]]
            return [i for i in possibilites if i in aux]

        return possibilites

    def __str__(self):
        text = '------------------\n'
        for i in self.board:
            text += str(i) + '\n'
        text += '------------------'
        return text


