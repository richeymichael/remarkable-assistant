# Remarkable Assistant
Creating an assistant to have more control over the remarkable tablet.

![](screenshots/screen.png)

# Warning
This software might brick your tablet. Don't use it if you don't know what
you're doing. 

# What does it do?
Currently you can only use it to change the sleep timeout, power off timeout, 
and the developer password.

# Download
There is currently a [DMG](bin/RemarkableAssistant.dmg) for Mac in the bin directory

# Installing and running the python directly
Install the requirements
`pip install -r requirements.txt`

Run the application
`python src/main.py`

# How to use it
1. Plug your remarkable tablet into your computer via USB
2. Set the old password the remarkable password you see under rM->About
3. Click the 'Attempt to Reconnect' button so the assistant will pull down your config
4. Remarkable Assistant should fill in the missing fields with the current values
5. You can now change the new password and timeout fields
6. When you're ready to save press the save settings to tablet button
7. Use the quit button to clean up temporary files

