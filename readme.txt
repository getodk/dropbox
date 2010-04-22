1. Download and install Python 2.6: <http://www.python.org/download>
2. Download CherryPy 3.1.2:
	- Windows installer <http://download.cherrypy.org/cherrypy/3.1.2/CherryPy-3.1.2.win32.exe>
		Download and run the installer.
	- tar.gz for Linux <http://download.cherrypy.org/cherrypy/3.1.2/CherryPy-3.1.2.tar.gz>
		Download, untar, and run "python setup.py install" in the cherrypy directory
3. Create a folder on your desktop (or a place of your choosing)
4. Save the attached file (odk_server.py) to that folder
5. Double click odk_server.py on Windows (or run "python odk_server.py" in that directory on Linux)
6. The server will create two sub-folder in your folder, data/ and forms/
7. Server will display a message looking something like this:
	
	Data directory: ./data/
	Forms directory: ./forms/
	Allowed file_types: ['xml', 'jpg', 'png']
	
	Launch Cherrypy...
	
	[05/Mar/2010:01:27:26] ENGINE Listening for SIGTERM.
	[05/Mar/2010:01:27:26] ENGINE Bus STARTING
	[05/Mar/2010:01:27:26] ENGINE Started monitor thread '_TimeoutMonitor'.
	[05/Mar/2010:01:27:26] ENGINE Serving on 0.0.0.0:80 <http://0.0.0.0/>
	[05/Mar/2010:01:27:26] ENGINE Bus STARTED
	
8. Download some ODK forms from the ODK site<http://code.google.com/p/open-data-kit/source/browse/#svn/resources/forms> and save them to the "forms" sub-folder that was just created.
9. You should be able to visit http://localhost/ on your machine and see a little submission form. Don't use the form... just note that it works (I will be replacing this with an instructions page on connecting to it with ODK Collect.
10. Figure out the IP address of the wireless adapter. For Windows fo to Start button > Run > type "cmd" (press Enter). Then type "ipconfig" and note the wireless adapter IP (e.g. 192.168.0.3). If you're on Linux, you should know how to do this :)
11. On your Android phone, connect to wireless, and in ODK Collect you can configure the server to the IP address to http://[address], where [address] is the IP you found above (e.g. 192.168.0.3)
12. Try to download a form from the server, fill it out and submit it.
13. Submitted data should appear in the "data" sub-folder that was created.

*Warnings:*
By default, the odk_server.py will create the data and forms sub-folder in whatever folder you run the server from. You can change this by adding switches in the command line, or in a windows shortcut.

E.g. usage:
C:\odk>odk_server.py -d "c:\path\to\my\data\folder" -f "c:\path\to\my\form\folder" -x "xml,jpg,png"

*Usage:*
Usage: odk_server.py [options]

Options:
  -h, --help            show this help message and exit

  -d DIR, --data_dir=DIR
                        Directory where submitted xforms data is stored.
                        Default: ./

  -f DIR, --forms_dir=DIR
                        Directory where broadcasted xforms are stored.
                        Default: ./

  -x LIST, --allowed_file_types=LIST
                        Comma-separated list of allowed file types.
                        Default: xml,jpg,png

  -p INT, --port=INT
                        Port on which the server should listen.
                        Default: 80

