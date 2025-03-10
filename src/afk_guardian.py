import cv2
import time
import threading
import numpy as np
from datetime import datetime, timedelta
from pynput import mouse, keyboard
from plyer import notification
import matplotlib.pyplot as plt
import os
import sys  # Add this import

class AFKGuardian:
    def __init__(self, afk_threshold=10):
        """
        Initialize the AFK Guardian.
        
        Args:
            afk_threshold: Time in seconds before user is considered AFK
        """
        self.afk_threshold = afk_threshold
        self.last_activity = time.time()
        self.is_face_present = False
        self.is_running = False
        self.activity_log = []
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        # Add eye cascade classifier
        self.eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')
        self.cap = None
        
        # Add face detection parameters
        self.face_detection_history = []  # Store recent face detection results
        self.face_history_size = 10  # Number of frames to consider for smoothing
        self.face_confidence_threshold = 0.3  # Minimum confidence to consider face present
        
        # Create data directory if it doesn't exist
        self.data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        os.makedirs(self.data_dir, exist_ok=True)
    
    def start(self):
        """Start monitoring user activity."""
        self.is_running = True
        
        # Start keyboard and mouse listeners with error handling
        try:
            self.keyboard_listener = keyboard.Listener(on_press=self._on_activity)
            self.mouse_listener = mouse.Listener(on_move=self._on_activity, 
                                          on_click=self._on_activity, 
                                          on_scroll=self._on_activity)
            self.keyboard_listener.start()
            self.mouse_listener.start()
        except Exception as e:
            print(f"Error starting input listeners: {e}")
            print("Please grant Accessibility permissions in System Preferences > Security & Privacy > Privacy > Accessibility")
        
        # Start webcam monitoring in a separate thread
        self.webcam_thread = threading.Thread(target=self._monitor_webcam)
        self.webcam_thread.daemon = True
        self.webcam_thread.start()
        
        # Start AFK checking in a separate thread
        self.afk_thread = threading.Thread(target=self._check_afk)
        self.afk_thread.daemon = True
        self.afk_thread.start()
        
        print("AFK Guardian started. Press Ctrl+C to stop.")
        print("Note: If you see permission errors, please check System Preferences > Security & Privacy > Privacy")
        print("      and grant permissions for Accessibility and Camera.")
        
        try:
            while self.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
    
    def stop(self):
        """Stop monitoring user activity."""
        self.is_running = False
        self.keyboard_listener.stop()
        self.mouse_listener.stop()
        if self.cap is not None:
            self.cap.release()
        cv2.destroyAllWindows()
        self._save_activity_log()
        print("AFK Guardian stopped.")
    
    def _on_activity(self, *args):
        """Update last activity timestamp when keyboard or mouse activity is detected."""
        self.last_activity = time.time()
    
    def _monitor_webcam(self):
        """Monitor webcam for face presence."""
        try:
            self.cap = cv2.VideoCapture(0)
            if not self.cap.isOpened():
                print("Warning: Could not open webcam. Face detection will be disabled.")
                print("Please grant Camera permissions in System Preferences > Security & Privacy > Privacy > Camera")
                return
            
            while self.is_running:
                ret, frame = self.cap.read()
                if not ret:
                    print("Failed to grab frame from webcam")
                    time.sleep(1)
                    continue
                    
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                
                # Apply histogram equalization to improve contrast
                gray = cv2.equalizeHist(gray)
                
                # Detect faces with more lenient parameters
                faces = self.face_cascade.detectMultiScale(
                    gray,
                    scaleFactor=1.1,  # More gradual scaling (was 1.3)
                    minNeighbors=3,   # Fewer neighbors required (was 5)
                    minSize=(30, 30),
                    flags=cv2.CASCADE_SCALE_IMAGE
                )
                
                # Calculate face confidence based on detection results
                face_confidence = self._calculate_face_confidence(faces, frame.shape)
                
                # Update face detection history
                self.face_detection_history.append(face_confidence)
                if len(self.face_detection_history) > self.face_history_size:
                    self.face_detection_history.pop(0)
                
                # Smooth face detection using recent history
                avg_confidence = sum(self.face_detection_history) / len(self.face_detection_history)
                self.is_face_present = avg_confidence >= self.face_confidence_threshold
                
                # Draw rectangle around faces (for debugging)
                for (x, y, w, h) in faces:
                    cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)
                    
                    # Detect eyes within each face region
                    roi_gray = gray[y:y+h, x:x+w]
                    roi_color = frame[y:y+h, x:x+w]
                    
                    # Improve eye detection by:
                    # 1. Using the upper half of the face for eye detection
                    # 2. Applying histogram equalization to improve contrast
                    # 3. Using more appropriate parameters for eye detection
                    eye_roi_gray = roi_gray[int(h*0.1):int(h*0.5), :]
                    eye_roi_gray = cv2.equalizeHist(eye_roi_gray)
                    eyes = self.eye_cascade.detectMultiScale(
                        eye_roi_gray,
                        scaleFactor=1.1,
                        minNeighbors=5,
                        minSize=(30, 30),
                        flags=cv2.CASCADE_SCALE_IMAGE
                    )
                    
                    # Draw rectangle around eyes (adjust coordinates to match the ROI offset)
                    for (ex, ey, ew, eh) in eyes:
                        # Adjust y-coordinate to account for the ROI offset
                        ey += int(h*0.1)
                        cv2.rectangle(roi_color, (ex, ey), (ex+ew, ey+eh), (0, 255, 0), 2)
                
                # Add face confidence display
                cv2.putText(frame, f"Face Confidence: {avg_confidence:.2f}", (10, 190), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                cv2.putText(frame, f"Face Present: {self.is_face_present}", (10, 230), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0) if self.is_face_present else (0, 0, 255), 2)
                
                # Display the resulting frame (comment out for production)
                cv2.imshow('AFK Guardian', frame)
                
                # Press 'q' to quit
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    self.is_running = False
                    break
                    
                time.sleep(0.1)  # Reduce CPU usage
        except Exception as e:
            print(f"Error in webcam monitoring: {e}")
            import traceback
            traceback.print_exc()
            self.is_face_present = False  # Assume no face if webcam fails
    
    def _calculate_face_confidence(self, faces, frame_shape):
        """
        Calculate face confidence based on detection results.
        
        Args:
            faces: List of detected faces (x, y, w, h)
            frame_shape: Shape of the frame (height, width, channels)
        
        Returns:
            float: Confidence value between 0 and 1
        """
        if len(faces) == 0:
            return 0.0
        
        # Calculate based on face size relative to frame
        frame_area = frame_shape[0] * frame_shape[1]
        face_areas = [w * h for (x, y, w, h) in faces]
        max_face_area = max(face_areas)
        
        # Calculate confidence based on face size and position
        # A centered, larger face has higher confidence
        max_confidence = 0.0
        for i, (x, y, w, h) in enumerate(faces):
            # Size factor (larger face = higher confidence)
            size_factor = face_areas[i] / frame_area
            
            # Position factor (centered face = higher confidence)
            center_x = x + w/2
            center_y = y + h/2
            frame_center_x = frame_shape[1] / 2
            frame_center_y = frame_shape[0] / 2
            
            # Calculate distance from center (normalized)
            distance_from_center = np.sqrt(
                ((center_x - frame_center_x) / frame_shape[1])**2 + 
                ((center_y - frame_center_y) / frame_shape[0])**2
            )
            position_factor = 1 - min(1, distance_from_center * 2)
            
            # Combine factors
            confidence = 0.7 * size_factor * 100 + 0.3 * position_factor
            confidence = min(1.0, confidence)
            
            max_confidence = max(max_confidence, confidence)
        
        return max_confidence
    
    def _check_afk(self):
        """Check if user is AFK and log activity."""
        last_status = "active"
        last_notification_time = 0
        
        while self.is_running:
            try:
                current_time = time.time()
                time_since_activity = current_time - self.last_activity
                
                # Determine current status
                if time_since_activity > self.afk_threshold and not self.is_face_present:
                    current_status = "afk"
                    # Only send notification once every 5 minutes
                    if last_status == "active" or (current_time - last_notification_time > 300):
                        self._send_notification("AFK Alert", "You've been away for too long!")
                        last_notification_time = current_time
                else:
                    current_status = "active"
                
                # Log status change
                if current_status != last_status:
                    self.activity_log.append({
                        'timestamp': datetime.now(),
                        'status': current_status
                    })
                    last_status = current_status
            except Exception as e:
                print(f"Error in AFK checking: {e}")
                
            time.sleep(1)
    
    def _send_notification(self, title, message):
        """Send a desktop notification."""
        try:
            notification.notify(
                title=title,
                message=message,
                app_name="AFK Guardian",
                timeout=10
            )
        except Exception as e:
            print(f"Failed to send notification: {e}")
    
    def _save_activity_log(self):
        """Save activity log to a file."""
        if not self.activity_log:
            return
            
        filename = os.path.join(self.data_dir, f"activity_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        with open(filename, 'w') as f:
            f.write("timestamp,status\n")
            for entry in self.activity_log:
                f.write(f"{entry['timestamp']},{entry['status']}\n")
        
        print(f"Activity log saved to {filename}")
    
    def generate_report(self, log_file=None):
        """Generate productivity report from activity log."""
        if log_file:
            # Load activity log from file
            self._load_activity_log(log_file)
        
        if not self.activity_log:
            print("No activity data available")
            return
        
        # Calculate active and AFK durations
        active_duration = timedelta()
        afk_duration = timedelta()
        
        for i in range(1, len(self.activity_log)):
            prev_entry = self.activity_log[i-1]
            curr_entry = self.activity_log[i]
            
            duration = curr_entry['timestamp'] - prev_entry['timestamp']
            
            if prev_entry['status'] == 'active':
                active_duration += duration
            else:
                afk_duration += duration
        
        # Plot the results
        labels = ['Active', 'AFK']
        sizes = [active_duration.total_seconds(), afk_duration.total_seconds()]
        
        plt.figure(figsize=(10, 6))
        
        # Pie chart
        plt.subplot(1, 2, 1)
        plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90)
        plt.axis('equal')
        plt.title('Activity Distribution')
        
        # Bar chart
        plt.subplot(1, 2, 2)
        plt.bar(labels, sizes, color=['green', 'red'])
        plt.ylabel('Time (seconds)')
        plt.title('Activity Duration')
        
        plt.tight_layout()
        
        # Save the plot
        plot_file = os.path.join(self.data_dir, f"activity_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        plt.savefig(plot_file)
        plt.close()
        
        print(f"Report generated and saved to {plot_file}")
        
        # Print summary
        total_time = active_duration + afk_duration
        active_percentage = (active_duration.total_seconds() / total_time.total_seconds()) * 100 if total_time.total_seconds() > 0 else 0
        
        print("\nActivity Summary:")
        print(f"Total monitoring time: {total_time}")
        print(f"Active time: {active_duration} ({active_percentage:.1f}%)")
        print(f"AFK time: {afk_duration} ({100-active_percentage:.1f}%)")
        
        return plot_file
    
    def _load_activity_log(self, log_file):
        """Load activity log from a file."""
        self.activity_log = []
        
        with open(log_file, 'r') as f:
            # Skip header
            next(f)
            
            for line in f:
                timestamp_str, status = line.strip().split(',')
                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
                
                self.activity_log.append({
                    'timestamp': timestamp,
                    'status': status
                })
    
    def show_camera_preview(self):
        """
        Show a camera preview window for demonstration purposes.
        This method tracks keyboard/mouse activity and displays it alongside face detection.
        """
        print("Starting camera preview. Press 'q' to quit.")
        
        # Initialize activity tracking
        self.last_activity = time.time()
        activity_status = "Active"
        
        # Create analytics data structures
        start_time = time.time()
        activity_history = []  # List of (timestamp, is_active, face_detected)
        
        # Start keyboard and mouse listeners
        try:
            keyboard_listener = keyboard.Listener(on_press=self._on_activity)
            mouse_listener = mouse.Listener(on_move=self._on_activity, 
                                      on_click=self._on_activity, 
                                      on_scroll=self._on_activity)
            keyboard_listener.start()
            mouse_listener.start()
        except Exception as e:
            print(f"Error starting input listeners: {e}")
            print("Please grant Accessibility permissions in System Preferences > Security & Privacy > Privacy > Accessibility")
        
        try:
            # Initialize the webcam
            self.cap = cv2.VideoCapture(0)
            if not self.cap.isOpened():
                print("Error: Could not open webcam.")
                print("Please grant Camera permissions in System Preferences > Security & Privacy > Privacy > Camera")
                return
            
            # Create a named window with a specific size
            cv2.namedWindow('AFK Guardian - Camera Preview', cv2.WINDOW_NORMAL)
            cv2.resizeWindow('AFK Guardian - Camera Preview', 1200, 800)
            
            # Create a separate window for analytics
            cv2.namedWindow('AFK Guardian - Analytics', cv2.WINDOW_NORMAL)
            cv2.resizeWindow('AFK Guardian - Analytics', 800, 400)
            
            # Create blank analytics image
            analytics_img = np.ones((400, 800, 3), dtype=np.uint8) * 255
            
            while True:
                # Read a frame from the webcam
                ret, frame = self.cap.read()
                if not ret:
                    print("Failed to grab frame from webcam")
                    time.sleep(1)
                    continue
                
                # Convert to grayscale for face detection
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.equalizeHist(gray)  # Improve contrast
                
                # Detect faces with more lenient parameters
                faces = self.face_cascade.detectMultiScale(
                    gray,
                    scaleFactor=1.1,
                    minNeighbors=3,
                    minSize=(30, 30),
                    flags=cv2.CASCADE_SCALE_IMAGE
                )
                
                # Calculate face confidence
                face_confidence = self._calculate_face_confidence(faces, frame.shape)
                
                # Update face detection history
                self.face_detection_history.append(face_confidence)
                if len(self.face_detection_history) > self.face_history_size:
                    self.face_detection_history.pop(0)
                
                # Smooth face detection using recent history
                avg_confidence = sum(self.face_detection_history) / len(self.face_detection_history)
                face_detected = avg_confidence >= self.face_confidence_threshold
                
                # Track if eyes are detected
                eyes_detected = False
                
                # Draw rectangle around faces
                for (x, y, w, h) in faces:
                    cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)
                    
                    # Detect eyes within each face region
                    roi_gray = gray[y:y+h, x:x+w]
                    roi_color = frame[y:y+h, x:x+w]
                    eyes = self.eye_cascade.detectMultiScale(roi_gray)
                    
                    # Draw rectangle around eyes
                    for (ex, ey, ew, eh) in eyes:
                        cv2.rectangle(roi_color, (ex, ey), (ex+ew, ey+eh), (0, 255, 0), 2)
                        eyes_detected = True
                
                # Check for keyboard/mouse activity
                current_time = time.time()
                time_since_activity = current_time - self.last_activity
                elapsed_time = current_time - start_time
                
                if time_since_activity < self.afk_threshold:
                    activity_status = "Active"
                    activity_color = (0, 255, 0)  # Green
                    is_active = 1
                else:
                    activity_status = "Inactive"
                    activity_color = (0, 0, 255)  # Red
                    is_active = 0
                
                # Record activity data
                activity_history.append((elapsed_time, is_active, int(face_detected)))
                
                # Add text to show face confidence
                cv2.putText(frame, f"Face Confidence: {avg_confidence:.2f}", (10, 190), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                
                # Add text to show if a face is detected
                face_status = f"Face Detected: {face_detected}"
                cv2.putText(frame, face_status, (10, 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0) if face_detected else (0, 0, 255), 2)
                
                # Add text to show if eyes are detected
                eye_status = f"Eyes Detected: {eyes_detected}"
                cv2.putText(frame, eye_status, (10, 150), 
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0) if eyes_detected else (0, 0, 255), 2)
                
                # Add text to show keyboard/mouse activity status
                cv2.putText(frame, f"Activity: {activity_status}", (10, 70), 
                            cv2.FONT_HERSHEY_SIMPLEX, 1, activity_color, 2)
                
                # Add text to show time since last activity
                cv2.putText(frame, f"Time since activity: {int(time_since_activity)}s", (10, 110), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                
                # Update analytics visualization
                if len(activity_history) > 1:
                    # Create a blank white image for analytics
                    analytics_img = np.ones((400, 800, 3), dtype=np.uint8) * 255
                    
                    # Draw activity timeline (last 60 seconds or all data if less)
                    max_time_window = 60  # seconds to display
                    current_time = activity_history[-1][0]
                    start_display_time = max(0, current_time - max_time_window)
                    
                    # Filter data for the time window
                    display_data = [point for point in activity_history if point[0] >= start_display_time]
                    
                    if len(display_data) > 1:
                        # Draw activity graph
                        graph_height = 150
                        graph_y_offset = 50
                        graph_width = 750
                        graph_x_offset = 25
                        
                        # Draw axes
                        cv2.line(analytics_img, 
                                (graph_x_offset, graph_y_offset + graph_height), 
                                (graph_x_offset + graph_width, graph_y_offset + graph_height), 
                                (0, 0, 0), 2)  # X-axis
                        cv2.line(analytics_img, 
                                (graph_x_offset, graph_y_offset), 
                                (graph_x_offset, graph_y_offset + graph_height), 
                                (0, 0, 0), 2)  # Y-axis
                        
                        # Draw activity line (green)
                        for i in range(1, len(display_data)):
                            x1 = graph_x_offset + int((display_data[i-1][0] - start_display_time) / max_time_window * graph_width)
                            y1 = graph_y_offset + graph_height - int(display_data[i-1][1] * graph_height * 0.8)
                            x2 = graph_x_offset + int((display_data[i][0] - start_display_time) / max_time_window * graph_width)
                            y2 = graph_y_offset + graph_height - int(display_data[i][1] * graph_height * 0.8)
                            cv2.line(analytics_img, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        
                        # Draw face detection line (blue)
                        for i in range(1, len(display_data)):
                            x1 = graph_x_offset + int((display_data[i-1][0] - start_display_time) / max_time_window * graph_width)
                            y1 = graph_y_offset + graph_height - int(display_data[i-1][2] * graph_height * 0.8)
                            x2 = graph_x_offset + int((display_data[i][0] - start_display_time) / max_time_window * graph_width)
                            y2 = graph_y_offset + graph_height - int(display_data[i][2] * graph_height * 0.8)
                            cv2.line(analytics_img, (x1, y1), (x2, y2), (255, 0, 0), 2)
                        
                        # Draw labels
                        cv2.putText(analytics_img, "Activity Timeline (last 60 seconds)", 
                                   (graph_x_offset, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
                        cv2.putText(analytics_img, "Activity", 
                                   (graph_x_offset + graph_width + 10, graph_y_offset + 50), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                        cv2.putText(analytics_img, "Face Detected", 
                                   (graph_x_offset + graph_width + 10, graph_y_offset + 80), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
                        
                        # Draw time labels on x-axis
                        cv2.putText(analytics_img, f"{int(start_display_time)}s", 
                                   (graph_x_offset - 10, graph_y_offset + graph_height + 20), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
                        cv2.putText(analytics_img, f"{int(current_time)}s", 
                                   (graph_x_offset + graph_width - 10, graph_y_offset + graph_height + 20), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
                    
                    # Draw activity statistics
                    stats_y = 250
                    active_time = sum(point[1] for point in activity_history)
                    face_time = sum(point[2] for point in activity_history)
                    total_time = len(activity_history)
                    
                    if total_time > 0:
                        active_percent = (active_time / total_time) * 100
                        face_percent = (face_time / total_time) * 100
                        
                        cv2.putText(analytics_img, f"Session Statistics:", 
                                   (50, stats_y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
                        cv2.putText(analytics_img, f"Active: {active_percent:.1f}% of time", 
                                   (50, stats_y + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)
                        cv2.putText(analytics_img, f"Face Detected: {face_percent:.1f}% of time", 
                                   (50, stats_y + 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)
                        cv2.putText(analytics_img, f"Session Duration: {int(elapsed_time)}s", 
                                   (50, stats_y + 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)
                
                # Display the analytics
                cv2.imshow('AFK Guardian - Analytics', analytics_img)
                
                # Display the camera frame
                cv2.imshow('AFK Guardian - Camera Preview', frame)
                
                # Press 'q' to quit
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                
                # Press 's' to save analytics data
                if cv2.waitKey(1) & 0xFF == ord('s'):
                    self._save_preview_analytics(activity_history)
                
                time.sleep(0.03)  # ~30 FPS
                
        except Exception as e:
            print(f"Error in camera preview: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Clean up
            if self.cap is not None:
                self.cap.release()
            cv2.destroyAllWindows()
            
            # Stop listeners
            try:
                keyboard_listener.stop()
                mouse_listener.stop()
            except:
                pass
            
            # Save analytics data
            if len(activity_history) > 0:
                self._save_preview_analytics(activity_history)
                
            print("Camera preview stopped.")
    
    def _save_preview_analytics(self, activity_history):
        """Save preview analytics data to a CSV file."""
        filename = os.path.join(self.data_dir, f"preview_analytics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        with open(filename, 'w') as f:
            f.write("elapsed_time,is_active,face_detected\n")
            for entry in activity_history:
                f.write(f"{entry[0]},{entry[1]},{entry[2]}\n")
        
        print(f"Analytics data saved to {filename}")

    def generate_heatmap(self, log_file=None):
        """Generate a heatmap showing activity patterns throughout the day."""
        if log_file:
            self._load_activity_log(log_file)
        
        if not self.activity_log:
            print("No activity data available")
            return
        
        # Create 24x7 matrix for week-long heatmap (hours x days)
        activity_matrix = np.zeros((24, 7))
        
        for i in range(1, len(self.activity_log)):
            prev_entry = self.activity_log[i-1]
            curr_entry = self.activity_log[i]
            
            if prev_entry['status'] == 'active':
                hour = prev_entry['timestamp'].hour
                day = prev_entry['timestamp'].weekday()
                duration = (curr_entry['timestamp'] - prev_entry['timestamp']).total_seconds() / 3600
                activity_matrix[hour, day] += duration
        
        # Plot heatmap
        plt.figure(figsize=(12, 8))
        plt.imshow(activity_matrix, cmap='YlOrRd', aspect='auto')
        plt.colorbar(label='Active Hours')
        plt.title('Weekly Activity Heatmap')
        plt.xlabel('Day of Week')
        plt.ylabel('Hour of Day')
        
        # Set tick labels
        days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        plt.xticks(range(7), days)
        plt.yticks(range(0, 24, 2))
        
        # Save plot
        plot_file = os.path.join(self.data_dir, f"activity_heatmap_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        plt.savefig(plot_file)
        plt.close()
        
        print(f"Heatmap saved to {plot_file}")

    def analyze_breaks(self, log_file=None):
        """Analyze break patterns and provide recommendations."""
        if log_file:
            self._load_activity_log(log_file)
        
        if not self.activity_log:
            print("No activity data available")
            return
        
        breaks = []
        current_break_start = None
        
        for entry in self.activity_log:
            if entry['status'] == 'afk':
                if current_break_start is None:
                    current_break_start = entry['timestamp']
            elif current_break_start is not None:
                break_duration = (entry['timestamp'] - current_break_start).total_seconds() / 60
                breaks.append(break_duration)
                current_break_start = None
        
        if not breaks:
            print("No breaks detected in the log")
            return
        
        # Calculate statistics
        avg_break = np.mean(breaks)
        max_break = np.max(breaks)
        min_break = np.min(breaks)
        total_breaks = len(breaks)
        
        # Plot break distribution
        plt.figure(figsize=(10, 6))
        plt.hist(breaks, bins=20, color='skyblue', edgecolor='black')
        plt.axvline(avg_break, color='red', linestyle='dashed', linewidth=2, label=f'Average ({avg_break:.1f} min)')
        plt.title('Break Duration Distribution')
        plt.xlabel('Break Duration (minutes)')
        plt.ylabel('Frequency')
        plt.legend()
        
        # Save plot
        plot_file = os.path.join(self.data_dir, f"break_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        plt.savefig(plot_file)
        plt.close()
        
        # Print analysis
        print("\nBreak Analysis:")
        print(f"Total breaks: {total_breaks}")
        print(f"Average break duration: {avg_break:.1f} minutes")
        print(f"Longest break: {max_break:.1f} minutes")
        print(f"Shortest break: {min_break:.1f} minutes")
        
        # Provide recommendations
        if avg_break < 5:
            print("\nRecommendation: Your breaks are too short. Consider taking longer breaks (5-15 minutes) every hour.")
        elif avg_break > 30:
            print("\nRecommendation: Your breaks are quite long. Consider taking more frequent but shorter breaks.")

    def calculate_productivity_score(self, log_file=None):
        """Calculate and visualize daily productivity scores."""
        if log_file:
            self._load_activity_log(log_file)
        
        if not self.activity_log:
            print("No activity data available")
            return
        
        # Group activities by day
        daily_scores = {}
        
        for i in range(1, len(self.activity_log)):
            prev_entry = self.activity_log[i-1]
            curr_entry = self.activity_log[i]
            
            date = prev_entry['timestamp'].date()
            duration = (curr_entry['timestamp'] - prev_entry['timestamp']).total_seconds() / 3600
            
            if date not in daily_scores:
                daily_scores[date] = {'active': 0, 'total': 0}
            
            daily_scores[date]['total'] += duration
            if prev_entry['status'] == 'active':
                daily_scores[date]['active'] += duration
        
        # Calculate scores and prepare plot data
        dates = []
        scores = []
        
        for date, data in sorted(daily_scores.items()):
            if data['total'] > 0:
                score = (data['active'] / data['total']) * 100
                dates.append(date)
                scores.append(score)
        
        # Plot productivity trend
        plt.figure(figsize=(12, 6))
        plt.plot(dates, scores, marker='o', linestyle='-', linewidth=2)
        plt.title('Daily Productivity Score Trend')
        plt.xlabel('Date')
        plt.ylabel('Productivity Score (%)')
        plt.grid(True)
        plt.xticks(rotation=45)
        
        # Save plot
        plot_file = os.path.join(self.data_dir, f"productivity_trend_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        plt.savefig(plot_file)
        plt.close()
        
        print(f"Productivity trend saved to {plot_file}")
        
        # Print recent scores
        print("\nRecent Productivity Scores:")
        for date, score in zip(dates[-5:], scores[-5:]):
            print(f"{date}: {score:.1f}%")