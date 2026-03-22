import { NavLink } from "react-router-dom";

const navLinks = [
  { to: "/", label: "Map" },
  { to: "/database", label: "Database" },
  { to: "/stats", label: "Statistics" },
  { to: "/about", label: "About" },
];

export default function Header() {
  return (
    <header className="bg-gray-900 border-b border-gray-800 px-4 py-0 flex items-center justify-between h-12 flex-shrink-0">
      <NavLink to="/" className="flex items-center gap-2">
        <span className="text-lg font-bold text-white tracking-tight">OSAF</span>
        <span className="text-xs text-gray-500 hidden sm:inline">
          Open Shark Attack File
        </span>
      </NavLink>

      <nav className="flex gap-1">
        {navLinks.map((link) => (
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
      </nav>
    </header>
  );
}
