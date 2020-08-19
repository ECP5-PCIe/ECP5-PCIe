# Generate all LFSR states in order and store to lfsr_states.csv in a '\n'-separated list as hexadecimal numbers with a preceding 0x

with open("lfsr_states.csv", "a") as file:

    state = 0xFFFF
    cnt = 0
    state = ((state >> 8) | ((state & 0xFF) << 8)) ^ ((state & 0xFF00) >> 5) ^ ((state & 0xFF00) >> 4) ^ ((state & 0xFF00) >> 3)
    cnt += 1
    print(cnt)
    file.write(hex(state))
    file.write("\n")
    while state != 0xFFFF:
        state = ((state >> 8) | ((state & 0xFF) << 8)) ^ ((state & 0xFF00) >> 5) ^ ((state & 0xFF00) >> 4) ^ ((state & 0xFF00) >> 3)
        file.write(hex(state))
        file.write("\n")
        cnt += 1
        print(cnt)
