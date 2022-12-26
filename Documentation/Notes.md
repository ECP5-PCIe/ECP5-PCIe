# LTSSM
## Detect
### Detect.Quiet
- Transmitter in electrical idle
- 2.5 GT/s, wait min. 1 ms if > 2.5 GT/s before
- LinkUp = 0b
- directed_speed_change = 0b
- upconfigure_capable = 0b
- idle_to_rlock_transitioned = 0b
- select_deemphasis see spec
- 12 ms or electrical idle broken -> Detect.Active

### Detect.Active
- Receiver detection on unconfigured lanes
- Polling if receivers detected on all unconfigured lanes
- Detect.Quiet if no receiver detected on all lanes
- Otherwise wait 12 ms and go to Polling when same lanes detect receiver as in first sequence

## Polling
### Polling.Active
- Link and Lane to `PAD`
- Enter Compliance (bit 4) of Link Control 2 is 1b -> Polling.Compliance
- 1024 TS1 Tx, 8 TS1 or TS2 Rx with link, lane `PAD` on all lanes -> Polling.Configuration
- After 24 ms: See spec

### Polling.Configuration
- Link and Lane to `PAD`, send TS2
- 8x TS2 `PAD` Rx, 16x TS2 Tx after 1x TS2 Rx -> Configuration
- 48 ms -> Detect