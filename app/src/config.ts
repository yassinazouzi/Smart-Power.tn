// Point at the local API during development; production builds use the public host.
export const API_URL = __DEV__ ? 'http://10.0.2.2:4000/v1' : 'https://api.smartpower.tn/v1';
