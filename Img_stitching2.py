# -*- coding: utf-8 -*-
"""Img stitching2.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1rQmeJf1KuJ49KHflaCjAiV8DbrnPqoAI
"""

import cv2
from pathlib import Path
import numpy as np

class VideMosaic:
    def __init__(self, first_image, output_height_times=3, output_width_times=1.2, detector_type="sift"):
        """Processes each frame and generates a stitched panorama."""
        self.detector_type = detector_type

        if detector_type == "sift":
            self.detector = cv2.SIFT_create(600)  # Increased keypoints for better matching
            index_params = dict(algorithm=1, trees=5)
            search_params = dict(checks=50)
            self.bf = cv2.FlannBasedMatcher(index_params, search_params)  # Faster than BFMatcher
        elif detector_type == "orb":
            self.detector = cv2.ORB_create(600)
            self.bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

        self.visualize = False  # Disabled visualization for speed
        self.process_first_frame(first_image)

        self.output_img = np.zeros(shape=(int(output_height_times * first_image.shape[0]),
                                          int(output_width_times * first_image.shape[1]), first_image.shape[2]))

        self.w_offset = int(self.output_img.shape[0] / 1 - first_image.shape[0] / 1)
        self.h_offset = int(self.output_img.shape[1] / 2 - first_image.shape[1] / 2)

        self.output_img[self.w_offset:self.w_offset+first_image.shape[0],
                        self.h_offset:self.h_offset+first_image.shape[1], :] = first_image

        self.H_old = np.eye(3)
        self.H_old[0, 2] = self.h_offset
        self.H_old[1, 2] = self.w_offset

    def process_first_frame(self, first_image):
        """Extracts keypoints from the first frame."""
        self.frame_prev = first_image
        frame_gray_prev = cv2.cvtColor(first_image, cv2.COLOR_BGR2GRAY)
        self.kp_prev, self.des_prev = self.detector.detectAndCompute(frame_gray_prev, None)

    def match(self, des_cur, des_prev):
        """Matches descriptors between frames."""
        if self.detector_type == "sift":
            pair_matches = self.bf.knnMatch(des_cur, des_prev, k=2)
            matches = [m for m, n in pair_matches if m.distance < 0.7 * n.distance]
        else:
            matches = self.bf.match(des_cur, des_prev)

        matches = sorted(matches, key=lambda x: x.distance)[:30]  # Keep best 30 matches
        return matches

    def process_frame(self, frame_cur):
        """Processes a new frame for mosaicing."""
        self.frame_cur = frame_cur  # Assign the frame before using it
        frame_gray_cur = cv2.cvtColor(frame_cur, cv2.COLOR_BGR2GRAY)
        self.kp_cur, self.des_cur = self.detector.detectAndCompute(frame_gray_cur, None)

        matches = self.match(self.des_cur, self.des_prev)
        if len(matches) < 4:
            return  # Skip frame if not enough matches

        self.H = self.findHomography(self.kp_cur, self.kp_prev, matches)
        self.H = np.matmul(self.H_old, self.H)
        self.warp(self.frame_cur, self.H)

        # Prepare for next frame
        self.H_old = self.H
        self.kp_prev, self.des_prev, self.frame_prev = self.kp_cur, self.des_cur, self.frame_cur

    @staticmethod
    def findHomography(image_1_kp, image_2_kp, matches):
        """Finds the best transformation matrix based on detected motion."""

        image_1_points = np.float32([image_1_kp[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
        image_2_points = np.float32([image_2_kp[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)

        # Compute displacement between matched keypoints
        displacements = image_2_points - image_1_points
        mean_displacement = np.mean(displacements, axis=0)[0]

        dx, dy = mean_displacement  # Extract average motion in x and y directions

        # Determine dominant movement
        if abs(dx) > abs(dy) * 1.5:
            print("Detected Horizontal Motion")
            transform_matrix, _ = cv2.estimateAffine2D(image_1_points, image_2_points, method=cv2.RANSAC)
        elif abs(dy) > abs(dx) * 1.5:
            print("Detected Vertical Motion")
            transform_matrix, _ = cv2.estimateAffine2D(image_1_points, image_2_points, method=cv2.RANSAC)
        else:
            print("Detected Diagonal/Complex Motion")
            transform_matrix, _ = cv2.findHomography(image_1_points, image_2_points, cv2.RANSAC)

        # Convert to 3x3 matrix if necessary
        if transform_matrix.shape == (2, 3):
            transform_matrix = np.vstack([transform_matrix, [0, 0, 1]])

        return transform_matrix

    def warp(self, frame_cur, H):
        """Applies the correct transformation (Affine or Homography) based on detected motion."""
        if H.shape == (2, 3):  # If it's an affine transformation (translation/rotation)
            warped_img = cv2.warpAffine(frame_cur, H,
                                        (self.output_img.shape[1], self.output_img.shape[0]),
                                        flags=cv2.INTER_LINEAR)
        else:  # If it's a full homography transformation
            warped_img = cv2.warpPerspective(frame_cur, H,
                                             (self.output_img.shape[1], self.output_img.shape[0]),
                                             flags=cv2.INTER_LINEAR)

        self.output_img[warped_img > 0] = warped_img[warped_img > 0]  # Merge images
        return self.output_img

def main():
    video_path = '/content/video_20250204_194625.mp4'
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        print("Error: Could not open video.")
        return

    is_first_frame = True
    video_mosaic = None

    while cap.isOpened():
        ret, frame_cur = cap.read()
        if not ret:
            if is_first_frame:
                print("Error: No frames found in video.")
                return
            break

        if is_first_frame:
            video_mosaic = VideMosaic(frame_cur, detector_type="sift")
            is_first_frame = False
            continue

        video_mosaic.process_frame(frame_cur)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

    if video_mosaic is not None:
        cv2.imwrite('mosaic.jpg', video_mosaic.output_img)
        print("Mosaic saved as mosaic.jpg")
    else:
        print("Error: No valid frames processed, mosaic not created.")


if __name__ == "__main__":
    main()
