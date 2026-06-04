class Piece:

    # Vertrag: ungueltige/unbekannte Typen ergeben eine LEERE Liste, NIE None.
    # So crasht 'for row in piece.form' im Solver nicht mehr mit
    # "NoneType is not iterable". Gueltige Typen 1..6 ueberschreiben das im
    # Konstruktor.
    form = []
    height = 0
    width = 0
    piece_type = 0

    # Steintyp -> (form, height, width). EINE Tabelle statt 6 identisch
    # strukturierter if/elif-Aeste; neue Typen werden hier (nicht im Code)
    # ergaenzt. Werte byte-identisch zur fruheren Verzweigung.
    _PIECE_DATA = {
        1: ([[1]],                 1, 1),
        2: ([[1], [1], [1]],       3, 1),
        3: ([[1, 1], [1, 1]],      2, 2),
        4: ([[1, 1, 0], [0, 1, 1]], 2, 3),
        5: ([[1, 0], [1, 1]],      2, 2),
        6: ([[1, 1], [0, 1]],      2, 2),
    }

    def __init__(self, type):
        data = self._PIECE_DATA.get(type)
        if data is not None:
            form, self.height, self.width = data
            # Frische Zeilen-Kopien: jede Instanz besitzt ihre eigene Form (wie
            # die fruheren Literale), damit die geteilte Tabelle nie aliased wird.
            self.form = [list(row) for row in form]
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
