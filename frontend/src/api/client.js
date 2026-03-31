import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL || "/api/v1";

const client = axios.create({
  baseURL: API_URL,
  headers: { "Content-Type": "application/json" },
  withCredentials: true, // Send httpOnly auth cookie with every request
});

export default client;
