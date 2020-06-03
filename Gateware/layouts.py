__all__ = ["ts_layout"]


ts_layout = [
    ("valid",       1),
    ("link", [
        ("valid",       1),
        ("number",      8),
    ]),
    ("lane", [
        ("valid",       1),
        ("number",      5),
    ]),
    ("n_fts",       8),
    ("rate",  [
        ("reserved0",   1),
        ("gen1",        1),
        ("gen2",        1),
        ("reserved1",   3),
        ("autonomous_change",   1),
        ("speed_change",        1),
    ]),
    ("ctrl",  [
        ("hot_reset",           1),
        ("disable_link",        1),
        ("loopback",            1),
        ("disable_scrambling",  1),
        ("compliance_receive",  1),
    ]),
    ("ts_id",       1), # 0: TS1, 1: TS2
]
