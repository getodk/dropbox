#!/usr/bin/python2.4
#
#
#  Copyright (C) 2010 Google Inc.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.


"""ODK Aggregate replacement.

  You must install Python 2.4+ (python.org) and Cherrypy (cherrypy.org)
  to using this server.

  This is an adaptation of the big file upload code sample from the Cherrypy
  wiki: http://tools.cherrypy.org/wiki/DirectToDiskFileUpload

  It has been modified to emulate the ODK Aggregate Java App Engine service
  that accepts data submission from the Android app ODK Collect.

  Xform xml data and multimedia is sent from ODK Collect as a multipart POST.
  Instead of storing this data in the App Engine datastore, files are simply
  written to the hard drive of the machine running this server.
"""

__author__ = 'alchemist@google.com (Sean Askay)'
__version__ = '0.1.2'


import cgi
import datetime
import glob
import optparse
import os
import re
import shutil
import tempfile
import cherrypy


def MakeDirIfAbsent(dir_name):
  """Creates a directory if does not exist."""
  if not os.path.isdir(dir_name):
    os.makedirs(dir_name)


# pylint: disable-msg=W0212
class TemporaryFileWrapper(tempfile._TemporaryFileWrapper):
  """Wrapper for TemporaryFiles() that doesn't delete tempfile on close.

  tempfile.NamedTemporaryFile() and TemporaryFile() delete their temp files
  after closing. In the original code sample provided on the Cherrypy wiki
  uses NamedTemporaryFiles() in conjunction with os.link() to move the temp
  file to a destired permanent location. But os.link() isn't supported on
  Windows, so there is no easy way to copy the temp file to a the final location
  before closing the temp file, which deletes it.

  NamedTemporaryFile() on python 2.6 has a delete parameter, which prevents the
  tempfile from being deleted. However, python 2.4 doesn't have this option.
  This workaround is used to provide backwards compatibility to Python 2.4.

  Code for wrapper was taken from Plone: http://svn.plone.org/svn/plone/
    plone.app.blob/trunk/src/plone/app/blob/monkey.py

  From their comments:
  [This is a] variant of tempfile._TemporaryFileWrapper that doesn't rely on the
  automatic windows behaviour of deleting closed files, which even
  happens, when the file has been moved -- e.g. to the blob storage,
  and doesn't complain about such a move either
  """

  unlink = staticmethod(os.unlink)
  isfile = staticmethod(os.path.isfile)

  def close(self):
    if not self.close_called:
      self.close_called = True
      self.file.close()

  def __del__(self):
    self.close()
    if self.isfile(self.name):
      self.unlink(self.name)


class CustomFieldStorage(cgi.FieldStorage):
  """Replacement for cgi.FieldStorage which uses custom tempfile handling.

  Uses the TemporaryFileWrapper() to create a tempfile that isn't deleted after
  closing.

  Below is the original customized FieldStorage from the Cherrypy wiki code
  sample. It doesn't provide windows compatibility, and was thus modified.

  class myFieldStorage(cgi.FieldStorage):
    '''Our version uses a named temporary file instead of the default
    non-named file; keeping it visible (named), allows us to create a
    2nd link after the upload is done, thus avoiding the overhead of
    making a copy to the destination filename.'''

    def make_file(self, binary=None):
        return tempfile.NamedTemporaryFile()
  """

  # pylint: disable-msg=W0613
  def make_file(self, binary=None):
    handle, name = tempfile.mkstemp()
    return TemporaryFileWrapper(os.fdopen(handle, 'w+b'), name)


# pylint: disable-msg=C6409
def noBodyProcess():
  """Overrides default Cherrypy handling to give direct control of submission.

  Sets cherrypy.request.process_request_body = False, giving us direct control
  of the file upload destination. By default cherrypy loads it to memory, we are
  directing it to disk.
  """

  cherrypy.request.process_request_body = False

# Override the default Cherrypy body processing in favor of noBodyProcess()
cherrypy.tools.noBodyProcess = cherrypy.Tool('before_request_body',
                                             noBodyProcess)


# pylint: disable-msg=C6409
class fileUpload(object):
  """fileUpload Cherrypy application.

  This application serves the following:

  - http://server/
    Returns a simple multipart HTML form which allows the testing of form
    submissions without needing to use an Android client. POSTs to ^submission

  - http://server/submission
    Accepts multipart POSTs from ODK Collect and
    writes attachments to disk. Returns HTTP 201 and a "Location" header of this
    server's address to confirm successful submission to the ODK client.

  - http://server/formList (not yet coded)
    Will provide an xml file which ODK Collect checks to see Xforms available
    on this server so it can download it to the Android phone.
  """

  def __init__(self, data_dir='./data/', forms_dir='./forms/',
               allowed_file_types='xml,jpg,png'):
    """Creates data and forms directories, sets allowed upload file types.

    Args:
      data_dir: A string containing the base path to the directory where
        POSTed data is saved
      forms_dir: A string containing the base path where forms downloadable by
        ODK Collect are stored
      allowed_file_types: A list of strings of allowed file extensions defining
        file types from the ODK Collect submission that will be stored on disk.

    Returns:
      Cherrypy reponse: HTTP 201 and "Location" header to client and the
        repsonse body as HTML string summarizing the files uploaded.
    """

    self.data_dir = data_dir
    self.forms_dir = forms_dir
    self.allowed_file_types = allowed_file_types.split(',')

  def MakeDataDirForForm(self, form_fields):
    """Creates a timestamped dir in data directory for this form.

    ODK Collect xml files are named like this: Basic_2010-01-01_00_00_00.xml.
    We want to organize form submissions by form name and time collected.
    If the form field contains a ".xml" extension and has a datestamp,
    then use the file name's prefix (e.g. Basic) for the first-level folder
    and the datestamp (e.g. 2010-01-01_00_00_00) for the second-level folder.

    Submissions missing an xml file, or ones where the xml file doesn't have a
    timestamp (probably meaning you are using the test upload page to
    test/debug) will use a first-level folder called "unnamed" and will create a
    second-level folder based on the system time.

    Args:
      form_fields: A dictionary of lists containing the POSTed multupart data.

    Returns:
      A timestamped directory path to the location where files should be stored.
    """

    form_name = 'unnamed'
    form_date = None
    for field in form_fields:
      file_name = form_fields[field].filename
      if file_name.endswith('.xml'):
        # ODK Collect xml files look like this: Basic_2010-03-03_01-49-09.xml
        date_pattern = re.compile(
            '^(.*)([0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}-[0-9]{2}-[0-9]{2})')
        match = date_pattern.search(file_name)
        if match:
          # Split the file name into form name prefix and datestamp suffix
          form_name = match.group(1).lower()
          form_date = match.group(2)
          break

    # If there isn't a datestamp in the xml file name, use the current sys time
    if not form_date:
      timestamp = datetime.datetime.now()
      form_date = timestamp.strftime('%Y-%m-%d_%H-%M-%S')

    form_dir = os.path.join(self.data_dir, form_name, form_date)
    MakeDirIfAbsent(form_dir)
    return form_dir

  @cherrypy.expose
  # pylint: disable-msg=C6409
  def index(self):
    """Returns a simple HTML form to test submissions.

    Note that the encoding type must be multipart/form-data.

    Args:
      None.

    Returns:
      An HTML form for testing submissions without needing to use ODK Collect.
    """

    return """
<html>
<body>
  <h3>ODK python server - Test form</h3>
  <p>This is a test form for the ODK python server.
     Uploaded files will be written to disk in the ./data/unnamed/
     directory</p>
  <p>Per the parameters used to start the server, only files with
     the following extensions will be written to disk after upload:<br>
     <b>%s</b></p>
  <form action="submission" method="post" enctype="multipart/form-data">
      File 1: <input type="file" name="file1"/> <br/>
      File 2: <input type="file" name="file2"/> <br/>
      <input type="submit"/>
  </form>
</body>
</html>
        """ % (', '.join(self.allowed_file_types))

  @cherrypy.expose
  # pylint: disable-msg=C6409
  def formList(self):
    """Returns an XML file with Xforms in the self.forms_dir directory.

    This Cherrypy action responds to requests at http://server/formList. This
    URL is expected by ODK Collect clients configured to use a server located
    at http://server/formList.

    This Cherry action looks for xml files in the self.forms_dir directory
    and returns another simple xml file which lists all the available forms.
    This xml file is requested by the ODK Collect client and allows the user
    to download forms from the server.

    Args:
      None

    Returns:
      Cherrypy reponse: HTTP 201 and "Location" header to client and the
        repsonse body as HTML string summarizing the files uploaded.
    """

    form_list_xml = '<forms>\n'
    for xml_form in glob.glob(os.path.join(self.forms_dir, '*.xml')):
      xml_form_base = os.path.basename(xml_form)
      # Shave off the .xml extension to get the form name
      form_name = os.path.splitext(xml_form_base)[0]
      form_url = 'http://%s/%s/%s' % (cherrypy.request.headers['Host'],
                                      'forms', xml_form_base)
      form_list_xml += '<form url="%s">%s</form>\n' % (form_url, form_name)
    form_list_xml += '</forms>\n'

    return form_list_xml

  @cherrypy.expose
  @cherrypy.tools.noBodyProcess()
  # pylint: disable-msg=C6409
  def submission(self):
    """Upload action, responds to multipart POST requests.

    This Cherrypy action responds to requests at http://server/submission, as
    expected by an ODK client per a setting that connects to a server
    at http://server.

    In order to confirm successful transmission of the data to the server,
    an HTTP 201 response with a "Location" header matching the original request
    from ODK Collect is returned.

    Args:
      None

    Returns:
      Cherrypy reponse: HTTP 201 and "Location" header to client and the
        repsonse body as HTML string summarizing the files uploaded.
    """

    # Default cherrypy timeout is 300s. Increased to 1hr for large files.
    cherrypy.response.timeout = 3600

    # Convert the header keys to lower case
    lc_headers = dict([k.lower(), v] for (k, v) in
                      cherrypy.request.headers.iteritems())

    # At this point we could limit the upload on content-length...
    # incomingBytes = int(lc_headers['content-length'])

    # Create our version of cgi.FieldStorage to parse the MIME encoded
    # form data where the file is contained
    form_fields = CustomFieldStorage(fp=cherrypy.request.rfile,
                                     headers=lc_headers,
                                     environ={'REQUEST_METHOD': 'POST'},
                                     keep_blank_values=True)

    # Make timestamped dir for this form submission, if doesn't already exist
    submission_dir = self.MakeDataDirForForm(form_fields)

    html_response = ''
    for field in form_fields:
      form_file = form_fields[field]
      ext = os.path.splitext(form_file.filename)[1]
      #remove the dot from the file extension
      ext = ext.replace('.', '')

      # Check form field for a file extension. If missing, continue.
      if ext not in self.allowed_file_types:
        # For now, we are just ignoring non-file fields in the POST request
        html_response += 'Server not configured to save "*.%s" files<br>' % ext
        continue

      # Prevent filenames that could cause moving up a directory
      target_file = form_file.filename.replace('../', '').replace('..\\', '')
      target_file_path = os.path.join(submission_dir, target_file)

      # If the file is really small (> 1KB), the cgi module loads it
      # as a cStringIO object, which has no "name" property,
      # which causes an AttributeError in original code sample.
      # So we must detect if this is a stringIO object instead of a tempfile:

      if not hasattr(form_file.file, 'name'):
        # Write contents of stringIO object to target file
        f = open(target_file_path, 'w+b')
        f.write(form_file.file.getvalue())
        f.close()
        form_file.file.close()
      else:
        # For tempfiles, move to the target location
        form_file.file.close()
        shutil.move(form_file.file.name, target_file_path)

      html_response += 'Stored: %s<br>' % target_file_path

    # ODK Collect looks for two things to consider a transfer of files
    # successful: 1) HTTP 201 response; and 2) the response "Location" header
    # to have the same host as the POST request was sent to. Using
    # cherrypy.request.headers['Host'] so this doesn't have to be hard-coded
    # See:
    #   http://open-data-kit.googlecode.com/svn/trunk/odk-collect/src/org/odk/
    #     collect/android/tasks/InstanceUploaderTask.java

    location = 'http://%s' % cherrypy.request.headers['Host']
    cherrypy.response.headers['Location'] = location
    cherrypy.response.status = 201
    return html_response


def main():
  usage = 'usage: %prog [options] arg'
  parser = optparse.OptionParser(usage)
  parser.add_option(
      '-d', '--data_dir', dest='data_dir', metavar='DIR', default='./data/',
      help='Directory where submitted xforms data is stored.')
  parser.add_option(
      '-f', '--forms_dir', dest='forms_dir', metavar='DIR', default='./forms/',
      help='Directory where broadcasted xforms are stored.')
  parser.add_option(
      '-x', '--allowed_file_types', dest='allowed_file_types', metavar='LIST',
      default='xml,jpg,png', help='Comma-separated list of allowed file types.')
  parser.add_option(
      '-p', '--port', dest='port', metavar='INT', default=80, type='int',
      help='Port on which the server should listen.')
  (options, unused_args) = parser.parse_args()

  print 'Data directory: %s' % options.data_dir
  print 'Forms directory: %s' % options.forms_dir
  print 'Allowed file_types: %s' % options.allowed_file_types.split(',')
  print
  print 'Launch Cherrypy...'
  print

  # Make sure the data and forms dirs exist before starting cherrypy
  # because we need to start serving static content out of the forms directory
  MakeDirIfAbsent(options.data_dir)
  MakeDirIfAbsent(options.forms_dir)

  # Configure Cherrypy to respond to all host requests on port 80
  cherrypy.config.update({'environment': 'production',
                          # Option to change the num of threads (deafault: 11)
                          # 'server.thread_pool': 11,
                          'server.socket_host': '0.0.0.0',
                          'server.socket_port': options.port,
                          'log.screen': True,
                         })

  # Set up site-wide config first so we get a log if errors occur.
  # Set up serving of static content from the forms directory
  conf = {'/forms': {'tools.staticdir.on': True,
                     'tools.staticdir.dir': os.path.abspath(options.forms_dir),
                     'tools.staticdir.content_types': {'xml': 'application/xml'}
                    }
         }

  # Remove any limit on the request body size; cherrypy's default is 100MB
  cherrypy.server.max_request_body_size = 0

  # Increase server socket timeout to 60s; we are more tolerant of bad
  # quality client-server connections (cherrypy's defult is 10s)
  cherrypy.server.socket_timeout = 60

  # Start up Cherrypy application
  app = fileUpload(
      data_dir=options.data_dir, forms_dir=options.forms_dir,
      allowed_file_types=options.allowed_file_types)
  cherrypy.quickstart(app, '/', config=conf)


if __name__ == '__main__':
  main()
