class Piece:

    # Vertrag: ungueltige/unbekannte Typen ergeben eine LEERE Liste, NIE None.
    # So crasht 'for row in piece.form' im Solver nicht mehr mit
    # "NoneType is not iterable". Gueltige Typen 1..6 ueberschreiben das im
    # Konstruktor.
    form = []
    height = 0
    width = 0
    piece_type = 0

    def __init__(self, type):

        if type == 1:
            self.form = [[1]]
            self.height = 1
            self.width = 1
            self.piece_type = type
        elif type == 2:
            self.form = [[1], [1], [1]]
            self.height = 3
            self.width = 1
            self.piece_type = type
        elif type == 3:
            self.form = [[1, 1], [1, 1]]
            self.height = 2
            self.width = 2
            self.piece_type = type
        elif type == 4:
            self.form = [[1, 1, 0], [0, 1, 1]]
            self.height = 2
            self.width = 3
            self.piece_type = type
        elif type == 5:
            self.form = [[1, 0], [1, 1]]
            self.height = 2
            self.width = 2
            self.piece_type = type
        elif type == 6:
            self.form = [[1, 1], [0, 1]]
            self.height = 2
            self.width = 2
            self.piece_type = type
        else:
            # Unbekannter Typ oder None -> sicherer, leerer Stein.
            self.form = []
            self.height = 0
            self.width = 0
            self.piece_type = 0

    @property
    def is_valid(self):
        """True nur fuer einen echten Stein (Typ 1..6 mit gesetzter Form)."""
        return self.piece_type in (1, 2, 3, 4, 5, 6) and bool(self.form)

    def __str__(self):
        text = '------------------\n'
        for i in self.form:
            text += str(i) + '\n'
        text += '------------------'
        return text
