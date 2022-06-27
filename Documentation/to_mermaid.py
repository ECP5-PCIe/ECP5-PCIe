with open("LTSSM.dot") as dotfile:
    lines = dotfile.readlines()

    transitions = []

    print("graph TD")

    recording = False
    for line in lines:
        if "// Transitions End" in line:
            recording = False
        
        if recording:
            parts = line.split("[")
            label = parts[1].split('"')[1].replace("|", "OR").replace("&", "AND").replace("^", "XOR").replace("\\n", "<br>")
            label = " "
            transition = parts[0].replace('"', "").replace("->", f'-->|"{label}"|')
            print(transition)

        if "// Transitions Start" in line:
            recording = True