import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "../api/useAuth";

export default function LoginPage() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({
    username: "",
    password: "",
    email: "",
    display_name: "",
  });
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(null);

  const handleChange = (e) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(form.username, form.password);
      navigate("/");
    } catch (err) {
      setError(err.response?.data?.detail || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const { register } = await import("../api/useAuth").then((m) => ({
        register: async (data) => {
          const client = (await import("../api/client")).default;
          return client.post("/auth/register", data);
        },
      }));
      await register({
        username: form.username,
        email: form.email,
        password: form.password,
        display_name: form.display_name || null,
      });
      setSuccess("Account created! You can now log in.");
      setMode("login");
    } catch (err) {
      setError(err.response?.data?.detail || "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex-1 flex items-center justify-center bg-gray-900">
      <div className="w-full max-w-sm">
        <h1 className="text-2xl font-bold text-white text-center mb-6">
          {mode === "login" ? "Sign In" : "Create Account"}
        </h1>

        {success && (
          <div className="bg-green-900/30 text-green-400 text-sm rounded-lg px-4 py-3 mb-4">
            {success}
          </div>
        )}

        {error && (
          <div className="bg-red-900/30 text-red-400 text-sm rounded-lg px-4 py-3 mb-4">
            {error}
          </div>
        )}

        <form
          onSubmit={mode === "login" ? handleLogin : handleRegister}
          className="space-y-4"
        >
          {mode === "register" && (
            <>
              <input
                name="email"
                type="email"
                required
                placeholder="Email"
                value={form.email}
                onChange={handleChange}
                className="w-full bg-gray-800 text-white rounded-lg px-4 py-2.5 border border-gray-700 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none placeholder-gray-500"
              />
              <input
                name="display_name"
                placeholder="Display name (optional)"
                value={form.display_name}
                onChange={handleChange}
                className="w-full bg-gray-800 text-white rounded-lg px-4 py-2.5 border border-gray-700 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none placeholder-gray-500"
              />
            </>
          )}

          <input
            name="username"
            required
            placeholder="Username"
            value={form.username}
            onChange={handleChange}
            className="w-full bg-gray-800 text-white rounded-lg px-4 py-2.5 border border-gray-700 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none placeholder-gray-500"
          />

          <input
            name="password"
            type="password"
            required
            placeholder="Password"
            value={form.password}
            onChange={handleChange}
            className="w-full bg-gray-800 text-white rounded-lg px-4 py-2.5 border border-gray-700 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none placeholder-gray-500"
          />

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 text-white rounded-lg py-2.5 font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {loading
              ? "..."
              : mode === "login"
                ? "Sign In"
                : "Create Account"}
          </button>
        </form>

        <p className="text-sm text-gray-500 text-center mt-4">
          {mode === "login" ? (
            <>
              Don't have an account?{" "}
              <button
                onClick={() => {
                  setMode("register");
                  setError(null);
                }}
                className="text-blue-400 hover:text-blue-300"
              >
                Register
              </button>
            </>
          ) : (
            <>
              Already have an account?{" "}
              <button
                onClick={() => {
                  setMode("login");
                  setError(null);
                }}
                className="text-blue-400 hover:text-blue-300"
              >
                Sign in
              </button>
            </>
          )}
        </p>
      </div>
    </div>
  );
}
