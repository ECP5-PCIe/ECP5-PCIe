To program the ispCLOCK chip:
`openocd -f ispCLOCK-x00MHz.svf`
where x is 1 or 2

To change a .jed file into a .svf file:
- Open Diamond Programmer
    - Click on `Design` -> `Utilities` -> `Deployment Tool`
    - Choose `File Conversion`
    - Click `OK`
- Click on the button labelled SVF in the top bar, the 8th button from the left
- Under the filename column, click in the field and choose the file
- Click on `Next`
- Check `Include RESET at the End of the SVF File`
- Click on `Next`
- Choose the output file location
- Click `Generate`
