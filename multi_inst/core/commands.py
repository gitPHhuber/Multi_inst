"""MSP command identifiers used across the project."""

from enum import IntEnum


class MSPCommand(IntEnum):
    MSP_API_VERSION = 1
    MSP_FC_VARIANT = 2
    MSP_FC_VERSION = 3
    MSP_BOARD_INFO = 4
    MSP_BUILD_INFO = 5
    MSP_NAME = 10
    MSP_STATUS = 101
    MSP_RAW_IMU = 102
    MSP_SERVO = 103
    MSP_MOTOR = 104
    MSP_RC = 105
    MSP_ATTITUDE = 108
    MSP_ALTITUDE = 109
    MSP_ANALOG = 110
    MSP_PID = 112
    MSP_VOLTAGE_METERS = 128
    MSP_CURRENT_METERS = 129
    MSP_BATTERY_STATE = 130
    MSP_STATUS_EX = 150
    MSP_UID = 160
