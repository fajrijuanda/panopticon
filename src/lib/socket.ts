import { io } from "socket.io-client";

// The local python backend URL
const SOCKET_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export const socket = io(SOCKET_URL, {
  autoConnect: false, // We will connect it strategically
});
