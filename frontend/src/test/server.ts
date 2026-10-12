import { setupServer } from "msw/node";

// Answers the app's fetch calls inside tests, the way the API would. Each test
// adds the handlers it needs with server.use(...); none outlive their test.
export const server = setupServer();
