/**
 * Created by igboyes on 03/05/17.
 */

const createRequestActionType = (root) => {
    return {
        REQUESTED: `${root}_REQUESTED`,
        SUCCEEDED: `${root}_SUCCEEDED`,
        FAILED: `${root}_FAILED`
    };
};

// Virus actionTypes
export const WS_UPDATE_VIRUS = "WS_UPDATE_VIRUS";
export const WS_REMOVE_VIRUS = "WS_REMOVE_VIRUS";

export const FIND_VIRUSES = createRequestActionType("FIND_VIRUSES");

export const GET_VIRUS_REQUESTED = "GET_VIRUS_REQUESTED";
export const GET_VIRUS_SUCCEEDED = "GET_VIRUS_SUCCEEDED";
export const GET_VIRUS_FAILED = "GET_VIRUS_FAILED";

export const CREATE_VIRUS_SET_NAME = "CREATE_VIRUS_SET_NAME";
export const CREATE_VIRUS_SET_ABBREVIATION = "CREATE_VIRUS_SET_ABBREVIATION";
export const CREATE_VIRUS_CLEAR = "CREATE_VIRUS_CLEAR";
export const CREATE_VIRUS_REQUESTED = "CREATE_VIRUS_REQUESTED";
export const CREATE_VIRUS_SUCCEEDED = "CREATE_VIRUS_SUCCEEDED";
export const CREATE_VIRUS_FAILED = "CREATE_VIRUS_FAILED";

export const EDIT_VIRUS_REQUESTED = "EDIT_VIRUS_REQUESTED";
export const EDIT_VIRUS_SUCCEEDED = "EDIT_VIRUS_SUCCEEDED";
export const EDIT_VIRUS_FAILED = "EDIT_VIRUS_FAILED";

export const REMOVE_VIRUS_REQUESTED = "REMOVE_VIRUS_REQUESTED";
export const REMOVE_VIRUS_SUCCEEDED = "REMOVE_VIRUS_SUCCEEDED";
export const REMOVE_VIRUS_FAILED = "REMOVE_VIRUS_FAILED";

// History actionTypes
export const FIND_HISTORY_REQUESTED = "FIND_HISTORY_REQUESTED";
export const FIND_HISTORY_SUCCEEDED = "FIND_HISTORY_SUCCEEDED";
export const FIND_HISTORY_FAILED = "FIND_HISTORY";

export const REMOVE_CHANGE_REQUESTED = "REMOVE_CHANGE_REQUESTED";
export const REMOVE_CHANGE_SUCCEEDED = "REMOVE_CHANGE_SUCCEEDED";
export const REMOVE_CHANGE_FAILED = "REMOVE_CHANGE_FAILED";

// Users actionTypes
export const LOAD_USERS = "LOAD_USERS";
export const CREATE_USER = "CREATE_USER";

// Account actionTypes
export const GET_ACCOUNT_REQUESTED = "GET_ACCOUNT_REQUESTED";
export const GET_ACCOUNT_SUCCEEDED = "GET_ACCOUNT_SUCCEEDED";
export const GET_ACCOUNT_FAILED = "GET_ACCOUNT_FAILED";
export const LOGOUT_REQUESTED = "LOGOUT_REQUESTED";
export const LOGOUT_SUCCEEDED = "LOGOUT_SUCCEEDED";

// Administrative setting actionTypes
export const GET_SETTINGS = createRequestActionType("GET_SETTINGS");
export const UPDATE_SETTINGS = createRequestActionType("UPDATE_SETTINGS");

export const SET_SOURCE_TYPE_VALUE = "SET_SOURCE_TYPE_VALUE";
export const SET_CONTROL_READAHEAD_TERM = "SET_CONTROL_READAHEAD_TERM";
export const GET_CONTROL_READAHEAD_REQUESTED = "GET_CONTROL_READAHEAD_REQUESTED";
export const GET_CONTROL_READAHEAD_SUCCEEDED = "GET_CONTROL_READAHEAD_SUCCEEDED";
export const GET_CONTROL_READAHEAD_FAILED = "GET_CONTROL_READAHEAD_FAILED";

export const LIST_USERS = createRequestActionType("LIST_USERS");



