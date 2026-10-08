from numpy.typing import NDArray
import numpy as np


def quarternion_to_dcm(quarternion: NDArray, transpose=False):
    """
    Transformation matrix of body wrt local level coordinates
    :param quaternions:
    :return:
    """

    # Normalise Quaternions
    quaternions = np.array(quaternions) / np.linalg.norm(quaternions)

    # Get quaternion components
    q0, q1, q2, q3 = quaternions

    # Calculate transformation matrix components
    l1 = np.square(q0) + np.square(q1) - np.square(q2) - np.square(q3)
    l2 = 2 * (q1 * q2 + q0 * q3)
    l3 = 2 * (q1 * q3 - q0 * q2)

    m1 = 2 * (q1 * q2 - q0 * q3)
    m2 = np.square(q0) - np.square(q1) + np.square(q2) - np.square(q3)
    m3 = 2 * (q2 * q3 + q0 * q1)

    n1 = 2 * (q0 * q2 + q1 * q3)
    n2 = 2 * (q2 * q3 - q0 * q1)
    n3 = np.square(q0) - np.square(q1) - np.square(q2) + np.square(q3)

    # Calculate transformation matrix
    dcm = np.array([[l1, l2, l3], [m1, m2, m3], [n1, n2, n3]])

    if transpose:
        return np.transpose(dcm)
    else:
        return dcm


def euler_to_quaternion(euler_angles, degrees=True):
    # Euler angles are defined as [roll, pitch, yaw], [phi, theta, psi], [z, y, x]
    if degrees:
        euler_angles = np.deg2rad(euler_angles)

    # Get Euler components
    psi, theta, phi = euler_angles

    # Calculate Quaternions
    q0 = np.cos(psi / 2) * np.cos(theta / 2) * np.cos(phi / 2) + np.sin(
        psi / 2
    ) * np.sin(theta / 2) * np.sin(phi / 2)
    q1 = np.cos(psi / 2) * np.cos(theta / 2) * np.sin(phi / 2) - np.sin(
        psi / 2
    ) * np.sin(theta / 2) * np.cos(phi / 2)
    q2 = np.cos(psi / 2) * np.sin(theta / 2) * np.cos(phi / 2) + np.sin(
        psi / 2
    ) * np.cos(theta / 2) * np.sin(phi / 2)
    q3 = np.sin(psi / 2) * np.cos(theta / 2) * np.cos(phi / 2) - np.cos(
        psi / 2
    ) * np.sin(theta / 2) * np.sin(phi / 2)

    # Combine quaternion components into matrix of row vectors
    quaternions = np.array([q0, q1, q2, q3])

    # Normalise Quaternions
    quaternions = np.array(quaternions) / np.linalg.norm(quaternions)

    return quaternions
