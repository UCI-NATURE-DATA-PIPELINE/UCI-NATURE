/** Auth feature wrappers around shared auth and Drive service calls. */
import {
  connectDrive,
  getGoogleAuthStartUrl,
  loginUser,
  logoutGoogleAuth
} from "../../services/api.js";

export function createAuthApi() {
  return {
    connectDrive,
    getGoogleAuthStartUrl,
    loginUser,
    logoutGoogleAuth
  };
}
