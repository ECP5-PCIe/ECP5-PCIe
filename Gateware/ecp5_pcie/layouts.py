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

ltssm_layout = [
    ("link", [
        ("speed", 1), # 0: 2.5, 1: 5
        ("up", 1), # Currently the only thing that is implemented
        ("training", 1),
        ("scrambling", 1), # And this too
        ("n_fts", 8),
    ]),
    ("recv_err", 2),
    ("presence",1),
    ("idle_to_rlock_transitioned", 8),
]

dllp_layout = [
    ("type", 4),        # Header type
    ("type_meta", 3),   # Metadata, for example virtual channel or power management type
    ("header", 8),      # Header, for FCs
    ("data", 12),       # Data for FCs or AckNak_Seq_Num
    ("valid", 1),       # CRC valid
]

dll_layout = [
    ("PH", 8),
    ("PD", 12),
    ("NPH", 8),
    ("NPD", 12),
    ("CPLH", 8),
    ("CPLD", 12),
]

dll_status = [
    ("retry_buffer_occupation", 8),
    ("receive_buffer_occupation", 8),
    ("tx_seq_num", 12),
    ("rx_seq_num", 12),
]