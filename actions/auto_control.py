from camera.LaneTracking import process_one_frame, make_coordinates, display_lines
import http.client
from PyQt5.QtGui import QImage
import cv2
import numpy as np
import requests
import math

# picar server info
HOST      = '192.168.2.2'
PORT 	  = '8000'

# BASE_URL is variant use to save the format of host and port
BASE_URL = 'http://' + HOST + ':'+ PORT + '/'

def connection_ok():
    """Check whetcher connection is ok

    Post a request to server, if connection ok, server will return http response 'ok'

    Args:
        none

    Returns:
        if connection ok, return True
        if connection not ok, return False

    Raises:
        none
    """
    cmd = 'connection_test'
    url = BASE_URL + cmd
    print('url: %s' % url)
    # if server find there is 'connection_test' in request url, server will response 'Ok'
    try:
        r = requests.get(url)
        if r.text == 'OK':
            return True
    except:
        return False

def __request__(url, times=10):
	for x in range(times):
		try:
			requests.get(url)
			return 0
		except :
			print("Connection error, try again")
	print("Abort")
	return -1

def run_action(cmd):
	"""Ask server to do sth, use in running mode

	Post requests to server, server will do what client want to do according to the url.
	This function for running mode

	Args:
		# ============== Back wheels =============
		'bwready' | 'forward' | 'backward' | 'stop'

		# ============== Front wheels =============
		'fwready' | 'fwleft' | 'fwright' |  'fwstraight'

		# ================ Camera =================
		'camready' | 'camleft' | 'camright' | 'camup' | 'camdown'
	"""
	# set the url include action information
	url = BASE_URL + 'run/?action=' + cmd
	print('url: %s'% url)
	# post request with url
	__request__(url)

def run_speed(speed):
	"""Ask server to set speed, use in running mode

	Post requests to server, server will set speed according to the url.
	This function for running mode.

	Args:
		'0'~'100'
	"""
	# Set set-speed url
	url = BASE_URL + 'run/?speed=' + str(speed)
	print('url: %s'% url)
	# Set speed
	__request__(url)

def QImageToMat(qimg):
    """RGB888"""
    #qimg = QImage()
    #qimg.load("/home/auss/Pictures/test.png")
    qimg = qimg.convertToFormat(QImage.Format_RGB888)
    qimg = qimg.rgbSwapped()
    #assert(qimg.byteCount() == qimg.width() * qimg.height() * 3)

    ptr = qimg.constBits()

    if not ptr:
        return

    ptr.setsize(qimg.byteCount())

    mat = np.array(ptr).reshape( qimg.height(), qimg.width(), 3)  #  Copies the data
    return mat

class QueryImage:
    """Query Image

    Query images form http. eg: queryImage = QueryImage(HOST)

    Attributes:
        host, port. Port default 8080, post need to set when creat a new object

    """

    def __init__(self, host, port=8080, argv="/?action=snapshot"):
        # default port 8080, the same as mjpg-streamer server
        self.host = host
        self.port = port
        self.argv = argv

    def queryImage(self):
        """Query Image

        Query images form http.eg:data = queryImage.queryImage()

        Args:
            None

        Return:
            returnmsg.read(), http response data
        """
        http_data = http.client.HTTPConnection(self.host, self.port)
        http_data.putrequest('GET', self.argv)
        http_data.putheader('Host', self.host)
        http_data.putheader('User-agent', 'python-http.client')
        http_data.putheader('Content-type', 'image/jpeg')
        http_data.endheaders()
        returnmsg = http_data.getresponse()

        return returnmsg.read()


# Make sure there is a connection to the picar server
while True:
    response = connection_ok()
    if response:
        break

# start query image service
queryImage = QueryImage(HOST)

# actuate rear wheels
run_speed(20)
run_action('forward')

# Define the codec and create VideoWriter object
# fourcc = cv2.VideoWriter_fourcc(*'XVID')
# out = cv2.VideoWriter('output.avi',fourcc, 20.0, (640,480))

######### history of m_angle and x_int_mid
num_history = 10
timestep = 20 # ms
history = [[0, 0] for x in range(num_history)]
cum_slope_error = 0 # integrate for I control
cum_x_int_mid_error = 0 # integrate for I control


# Get images and calculate steering angle
while True:

    # Get image from camera
    response = queryImage.queryImage()
    if not response:
        print('no response from querying images')
        continue

    qImage = QImage()
    qImage.loadFromData(response)
    image = QImageToMat(qImage)


    # make copy of raw image
    lane_image = np.copy(image)

    # write to video writer
    # out.write(lane_image)

    output_image, canny_image, averaged_lines, averaged_line = process_one_frame(image)

    angle = 0
    angle_max = 45

    ######## adjust these numbers
    x_int_mid_min = 50
    image_mid_offset = 0
    x_int_max_actuate = 300
    extra_px_below_image = 400
    Pm = .001
    Px = .001
    Im = .01
    Ix = .01

    # Calculate the slope and x-int
    try:
        print(averaged_lines)
        x1, y1, x2, y2 = averaged_line
        m = (y2 - y1) / (x2 - x1)
        m_angle = math.degrees(math.atan(1/m)) # right is positive
        b = y1 - m*x1
        x_int_mid = (image.shape[0] + extra_px_below_image - b)/m - (image.shape[1]/2 + image_mid_offset)
        print('slope', str(m_angle) + 'deg')
        print('x-int from middle', x_int_mid)

    except:
        # stop everything if no middle line is detected
        m_angle = 0
        x_int_mid = 0
        print('no averaged line')
        run_action('stop')
        break

    # Add to history
    history.insert(0, [m_angle, x_int_mid])
    history = history[:-1]

    # Control the steering
    h_avg = np.average(history, axis=0)
    h_sum = np.sum(history, axis=0)

    # err and integrate
    m = h_avg[0]
    x = h_avg[1]
    cum_slope_error = h_sum[0]
    cum_x_int_mid_error = h_sum[1]

    print('err and integrate')
    print(m, x, int(cum_slope_error), int(cum_x_int_mid_error))
    print(Pm*m, Px*x, int(Im*cum_slope_error), int(Ix*cum_x_int_mid_error))
    angle = Pm*m + Px*x + Im*cum_slope_error + Ix*cum_x_int_mid_error


    # Actuate, angles in the car go from 45 (full left) to 135 (full right)
    print(angle, 'deg')
    angle = angle + 90
    angle = max(min(angle, 135), 45)
    run_action('fwturn:' + str(int(angle)))

    # Show image
    time_averaged_fit = np.average(history, axis=0)
    time_averaged_line = np.array([
        image.shape[1]/2 + time_averaged_fit[1] + image_mid_offset, image.shape[0] + extra_px_below_image,
        (image.shape[1]/2 + time_averaged_fit[1] + image_mid_offset) + 800*math.tan(math.radians(-time_averaged_fit[0])), image.shape[0] + extra_px_below_image - 800
    ]).astype('int')
    time_averaged_line_image = display_lines(output_image, [time_averaged_line], color=(255, 0, 0))
    end_image = cv2.addWeighted(output_image, 0.8, time_averaged_line_image, 1, 1)

    cv2.imshow('result', end_image)
    if cv2.waitKey(timestep) == 27:
        continue

# out.release()
cv2.destroyAllWindows()