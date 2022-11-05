# Matthew R. Jones - SID 11566314 HW3
# Credit to some random internet denizen here # https://stackoverflow.com/questions/2408560/non-blocking-console-input
# for the idea of using threads to (sort of) get around the problem with console-only IO, though admittedly I really
# just took the idea of threads and ran with it rather than bothered reusing anything, because there were some serious
# issues with their implementation...

import socket
import keyboard
import threading
import random

HOST = "127.0.0.1"  # Set to localhost by default.
# Send/Recv port.
PORT = 55055
# Name (default pseud) of the client.
NAME = "Client: "
# Control flag for text input. If true, we have spawned a thread to handle text input and console writes (outside of that thread) are accumulating.
INTERFACE_OPEN = False
# Define the name of our listening socket object.
SOCKET_LISTENER = None
# Define the name of our socket connection.
CONN = None
# And its address.
ADDR = None
# And make sure we can find its handle later to close it.
SOCKET_HANDLE = None
# Delay is a problem... tell the program to chill.
SOCKET_HANDLE_ESTABLISHED = False

# Containers for message and file objects. Need these for message syncing.
message_queue = []
message_handles = {}
file_handles = {}

# Common functionality between server and client instance.
def display_help_menu(args=[]):
    global NAME
    print("/h : Display the command list.")
    print("/i <address> : Reconfigure the target IP address for port opening. IPv4 only, please. No error checking, so don't mess it up.")
    print("/p <portnumber> : Reconfigure the target port (for client) or listening port (for server).")
    print("/n <string> : Change your displayed name - will not affect previously sent messages.")
    print("/o : Initiate a connection (client) or begin listening (server)")
    print("   : If no values are supplied with /i and /p beforehand, will default to '127.0.0.1:55055'.")
    print("/m <string> : Attempt to send a message to server (if client) or client (if server).")
    print("/x : Exit the command interface, instruct system to display any queued messages into the terminal.")
    print("/z : Close all active ports and shut down the program instance.")
    print(NAME + ">> ", end="")

def change_ip(args=[]):
    global HOST, NAME
    HOST = args.strip()
    print("Target IP changed to '", HOST, "', if this is wrong you should probably fix it before calling /o.")
    print(NAME + ">> ", end="")

def change_port(args=[]):
    global PORT, NAME
    PORT = int(args.strip())
    print("Target port changed to '", str(PORT), "', if this is wrong you should probably fix it before calling /o.")
    print(NAME + ">> ", end="")

def rename(args=[]):
    global NAME
    NAME = args.strip()
    print("Console name has been changed to '", NAME, "'.")
    print(NAME + ">> ", end="")

def exit_command(args=[]):
    global INTERFACE_OPEN, message_queue
    INTERFACE_OPEN = False
    print("Exiting command interface. Refreshing your chat messages...\n  ---  Message Resume  ---  ")
    for i in message_queue:
        print("MSG : " + i)
    message_queue = []

def shutdown(args=[]):
    global INSTANCE_RUNNING
    INSTANCE_RUNNING = False
    print("Goodbye.")

def msg(args=[]):
    global NAME, SOCKET_HANDLE
    # If we have a valid connection... slice our message up into nice segments (1024-64 = 960 chars per)
    if SOCKET_HANDLE is not None and SOCKET_HANDLE_ESTABLISHED:
        msg = args.strip()
        # Build a message header.
        # Message header is a 64 char prefix formatted as follows.
        # xxx|xxx|xxxxxxxxxxxxxxx|-------------------------------|
        # 4 char - a three character flag designating what the payload is for (MSG for message, FIL for file) followed by 'pipe'
        # 4 char - LBX|, LB1| or LB0|. For files or messages packet counts greater than 10^15, LB?| will be set to LB1|, indicating that the message
        # exceeded the 960 character limit so many times that the object counter needs to loop back around to '000000000000000|' to keep track
        # of which packet this is. Given that this would require a call to transmit over a PETABYTE of information, I remain so
        # unconcerned about exceeding the limit that I never bothered implementing it anyway. LBX indicates this is the last packet of the sequence.
        # 16 char - a number representing the object counter for the payload. For longer messages, this will increment from 0 to indicate
        # that the message needs to be held until we can display it all. For short messages will always be 000000000000000|
        # 32 char - a handle to associate the file/msg to, if any. With files this will be a file name, but with messages could be anything provided it is
        # unique and consistent across the message transmission.
        # 8 char - 7 empty chars plus a terminal | - an identifier representing a unique message/file.
        #mheader = "MSG|LB0|000000000000000|-------------------------------|-------|"
        mlen = len(msg)
        mremainder = mlen
        msent = 0
        sent_count = 0
        random.seed()
        msgid = str(random.randint(1,9999999999999999999999999999999)).rjust(31, '0') + "|"
        while mremainder != 0:
            mheader = "MSG|"
            # Grab the 'next' chunk of the message, starting where we left off (or 0) and ending at where we started plus either our maximum
            # message size (960), or the remainder of the message.
            mtosend = msg[msent:msent + min(960, mremainder)]
            # Update our counters.
            mremainder -= len(mtosend)
            msent += len(mtosend)
            # If we are at the end of our send, flag it as such.
            if mremainder == 0:
                mheader += "LBX|"
            else:
                mheader += "LB0|"
            # Add our message count.
            mheader += str(sent_count).rjust(15, '0') + "|"
            # then update our counter.
            sent_count += 1
            # And add our unique message value and filler.
            mheader += msgid + "-------|"
            # Pack our message.
            mpack = mheader + mtosend
            SOCKET_HANDLE.sendall(bytes(mpack, 'ascii'))
    print(NAME + ">> ", end="")

def data_handle(data, message_handles, message_queue, file_handles):
    global NAME
    header = data[0:64]
    body = data[64:]
    mode = header[0:3]
    label = header[4:7]
    counter = header[8:24]
    id = header[24:55]
    id = id.strip()
    testbytes = header[56:64]
    # If we have a message.
    if mode == "MSG":
        # If the message terminates...
        if label == "LBX":
            # If we have an entry in our handles...
            if id in message_handles.keys():
                # Append it, then dump the whole thing to our queue and remove our ref in the handles.
                message_handles[id].append(body)
                message_queue.append(message_handles[id])
                del message_handles[id]
            # Otherwise it was a single packet message. Just dump to queue directly.
            else:
                message_queue.append(body)
        # Message doesnt terminate, need to make sure we have all of it before queuing.
        elif label == "LB0":
            # Make an entry or append as needed.
            if id in message_handles.keys():
                message_handles[id].append(body)
            else:
                message_handles[id] = body
    elif mode == "FIL":
        id = "copy-of-" + id
        if label == "LBX":
            # If we have an entry in our handles for the file already, write then close.
            if id in file_handles.keys():
                # Write, then close dump the whole thing to our queue and remove our ref in the handles.
                file_handles[id].write(body)
                file_handles[id].close()
                del file_handles[id]
            # Otherwise it was a single packet message. Just dump to a file directly.
            else:
                try:
                    file = open(id, "w")
                    file.write(body)
                    file.close()
                except:
                    print(NAME + "Unable to open or write file handle for filename '" + str(id) + "'. Ignoring transmission.")
                finally:
                    pass
        # Message doesnt terminate, need to make sure we have all of it before queuing.
        elif label == "LB0":
            # Make an entry or append as needed.
            if id in file_handles.keys():
                file_handles[id].write(body)
            else:
                try:
                    file = open(id, "w")
                    file_handles[id] = file
                    file_handles[id].write(body)
                except:
                    print(NAME + "Unable to open or write file handle for filename '" + str(id) + "'. Ignoring transmission.")
                    if id in file_handles.keys():
                        del file_handles[id]
                finally:
                    pass
        
def ftp(args=[]):
    global SOCKET_HANDLE, NAME
    if SOCKET_HANDLE is not None and SOCKET_HANDLE_ESTABLISHED:
        msg = args.strip()
        try:
            import os
            print (os.getcwd())
            file = open(msg, 'r')
        except:
            print("Could not open file '" + str(msg) + "' to read. Terminating.")
            return
        finally:
            filedata = file.read()        
            # Build a message header.
            # Message header is a 64 char prefix formatted as follows.
            # xxx|xxx|xxxxxxxxxxxxxxx|-------------------------------|
            # 4 char - a three character flag designating what the payload is for (MSG for message, FIL for file) followed by 'pipe'
            # 4 char - LBX|, LB1| or LB0|. For files or messages packet counts greater than 10^15, LB?| will be set to LB1|, indicating that the message
            # exceeded the 960 character limit so many times that the object counter needs to loop back around to '000000000000000|' to keep track
            # of which packet this is. Given that this would require a call to transmit over a PETABYTE of information, I remain so
            # unconcerned about exceeding the limit that I never bothered implementing it anyway. LBX indicates this is the last packet of the sequence.
            # 16 char - a number representing the object counter for the payload. For longer messages, this will increment from 0 to indicate
            # that the message needs to be held until we can display it all. For short messages will always be 000000000000000|
            # 32 char - a handle to associate the file/msg to, if any. With files this will be a file name, but with messages could be anything provided it is
            # unique and consistent across the message transmission.
            # 8 char - 7 empty chars plus a terminal | - an identifier representing a unique message/file.
            #mheader = "MSG|LB0|000000000000000|-------------------------------|-------|"

            # Read the entire file into memory (lazy I know, but unless we are sending entire libraries it is fine.)
            # Then just do what we did for message sending, but with file data.
            mlen = len(filedata)
            mremainder = mlen
            msent = 0
            sent_count = 0
            msgid = str(msg).ljust(31) + "|"
            while mremainder != 0:
                mheader = "FIL|"
                # Grab the 'next' chunk of the message, starting where we left off (or 0) and ending at where we started plus either our maximum
                # message size (960), or the remainder of the message.
                mtosend = filedata[msent:msent + min(960, mremainder)]
                # Update our counters.
                mremainder -= len(mtosend)
                msent += len(mtosend)
                # If we are at the end of our send, flag it as such.
                if mremainder == 0:
                    mheader += "LBX|"
                else:
                    mheader += "LB0|"
                # Add our message count.
                mheader += str(sent_count).rjust(15, '0') + "|"
                # then update our counter.
                sent_count += 1
                # And add our unique message value and filler.
                mheader += msgid + "-------|"
                # Pack our message.
                mpack = mheader + mtosend
                SOCKET_HANDLE.sendall(bytes(mpack, 'ascii'))
    print(NAME + ">> ", end="")


# Since this is instance dependent, declare it outside of common functionality.
def system_connect(args=[]):
    global CONN, ADDR, SOCKET_HANDLE, NAME, SOCKET_HANDLE_ESTABLISHED
    print(NAME, "Server is currently waiting for a connection. Connect your client now.")
    SOCKET_HANDLE = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    SOCKET_HANDLE.connect((HOST, PORT))  
    print(NAME + " Connection established to server")
    SOCKET_HANDLE_ESTABLISHED = True

# Build a lookup for our dictionary of things we can do.
CMD_DICT = {'/h': display_help_menu, '/i': change_ip, '/p' : change_port, '/n' : rename, '/o' : system_connect, '/m' : msg, '/f' : ftp, '/x' : exit_command, '/z' : shutdown}

# Command interface thread spawner. Called only when the keybind (set immediately below the function definition) is called.
def command_interface():
    global INTERFACE_OPEN
    if INTERFACE_OPEN:
        pass
    else:
    # Spawn a CI thread.
        INTERFACE_OPEN = True
        ci = CI()
        ci.run()

# Bind the hotkey 'ctrl plus alt' to the command interface trigger for the server CI. This is how we will let users type things into the console.
keyboard.add_hotkey('ctrl+alt', command_interface)

# Thread control for the command interface - spawned by hotkey detection - or by a direct call once the program begins.
class CI (threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
    def run (self):
        global INTERFACE_OPEN, CMD_DICT
        # While we have an open interface, poll for commands.
        while INTERFACE_OPEN:
            inp = input().strip()
            # Format them. Error check them.
            if len(inp) >= 2:
                cmd, args = inp[0:2], inp[2:]
                if cmd in CMD_DICT.keys():
                    # If they are OKed, run them.
                    CMD_DICT[cmd](args)
                else:
                    print("Command not found. To list valid commands, run /h")
            else:
                print("Command not found. To list valid commands, run /h")

# BEGIN PROGRAM EXECUTION.

print(NAME + "Client is pre configured to connect to a server ip:port of " + HOST + ":" + str(PORT))
print(NAME + "You may override this using /i <address> and /p <portnumber>.")
print(NAME + "For command list, enter /h. To enable command capture at any time press 'lctrl+lalt'. Exit with /x.")

INTERFACE_OPEN = False
#command_interface()

INSTANCE_RUNNING = True

while INSTANCE_RUNNING:
    # If we have a valid connection.
    if SOCKET_HANDLE_ESTABLISHED:
        data = str(SOCKET_HANDLE.recv(1024))
        try:
            data_handle(data[2:-1], message_handles, message_queue, file_handles)
        except:
            print(NAME + "Something went wrong... Couldn't parse received data.")
        finally:
            pass
    else:
        pass
    if not INTERFACE_OPEN:
        for i in message_queue:
            print("MSG : " + i)
        message_queue = []
            

# Server closed out.
for i in file_handles.keys():
    file_handles[i].close()
SOCKET_HANDLE.close()


#send = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#send.connect((HOST, PORT))
#while True:
    #send.sendall(b"Hello, world")
    #time.sleep(1.0)

    #data = send.recv(1024)

    #print(f"Received {data!r}")