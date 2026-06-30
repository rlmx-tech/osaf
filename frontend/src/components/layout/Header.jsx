import { NavLink } from "react-router-dom";
import { useAuth } from "../../api/useAuth";

const publicLinks = [
  { to: "/", label: "Map" },
  { to: "/database", label: "Database" },
  { to: "/news", label: "News" },
  { to: "/stats", label: "Statistics" },
  { to: "/about", label: "About" },
];

export default function Header() {
  const { isAuthenticated, isAdmin, user, logout } = useAuth();

  return (
    <header className="bg-gray-900 border-b border-gray-800 px-4 py-0 flex items-center justify-between h-12 flex-shrink-0">
      <NavLink to="/" className="flex items-center gap-2">
        <span className="text-lg font-bold text-white tracking-tight">OSAF</span>
        <span className="text-xs text-gray-500 hidden sm:inline">
          Open Shark Attack File
        </span>
      </NavLink>

      <nav className="flex items-center gap-1">
        {publicLinks.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            className={({ isActive }) =>
              `text-sm px-3 py-1.5 rounded transition-colors ${
                isActive
                  ? "bg-gray-800 text-white"
                  : "text-gray-400 hover:text-white hover:bg-gray-800/50"
              }`
            }
          >
            {link.label}
          </NavLink>
        ))}

        {isAuthenticated && (
          <NavLink
            to="/submit"
            className={({ isActive }) =>
              `text-sm px-3 py-1.5 rounded transition-colors ${
                isActive
                  ? "bg-gray-800 text-white"
                  : "text-gray-400 hover:text-white hover:bg-gray-800/50"
              }`
            }
          >
            Submit
          </NavLink>
        )}

        {isAdmin && (
          <NavLink
            to="/admin"
            className={({ isActive }) =>
              `text-sm px-3 py-1.5 rounded transition-colors ${
                isActive
                  ? "bg-gray-800 text-white"
                  : "text-amber-400/70 hover:text-amber-300 hover:bg-gray-800/50"
              }`
            }
          >
            Admin
          </NavLink>
        )}

        <span className="w-px h-5 bg-gray-700 mx-1" />

        {isAuthenticated ? (
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500">
              {user.username}
              {user.role !== "public" && (
                <span className="ml-1 text-blue-400/70">({user.role.replace("_", " ")})</span>
              )}
            </span>
            <button
              onClick={logout}
              className="text-xs text-gray-400 hover:text-white px-2 py-1 rounded hover:bg-gray-800/50"
            >
              Sign out
            </button>
          </div>
        ) : (
          <NavLink
            to="/login"
            className={({ isActive }) =>
              `text-sm px-3 py-1.5 rounded transition-colors ${
                isActive
                  ? "bg-gray-800 text-white"
                  : "text-gray-400 hover:text-white hover:bg-gray-800/50"
              }`
            }
          >
            Sign in
          </NavLink>
        )}
      </nav>
    </header>
  );
}
