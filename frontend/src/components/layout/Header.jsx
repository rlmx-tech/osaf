import { useState } from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../../api/useAuth";

const publicLinks = [
  { to: "/", label: "Map" },
  { to: "/database", label: "Database" },
  { to: "/news", label: "News" },
  { to: "/stats", label: "Statistics" },
  { to: "/about", label: "About" },
];

const navLinkClass = ({ isActive }) =>
  `text-sm px-3 py-2 rounded-md transition-colors ${
    isActive
      ? "bg-gray-800 text-white"
      : "text-gray-400 hover:text-white hover:bg-gray-800/60"
  }`;

export default function Header() {
  const { isAuthenticated, isAdmin, user, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  const closeMenu = () => setMenuOpen(false);

  const links = (
    <>
      {publicLinks.map((link) => (
        <NavLink key={link.to} to={link.to} onClick={closeMenu} className={navLinkClass}>
          {link.label}
        </NavLink>
      ))}

      {isAuthenticated && (
        <NavLink to="/submit" onClick={closeMenu} className={navLinkClass}>
          Submit
        </NavLink>
      )}

      {isAdmin && (
        <NavLink
          to="/admin"
          onClick={closeMenu}
          className={({ isActive }) =>
            `${navLinkClass({ isActive })} ${isActive ? "" : "text-amber-400/80"}`
          }
        >
          Admin
        </NavLink>
      )}
    </>
  );

  return (
    <header className="relative z-[2000] h-14 flex-shrink-0 border-b border-gray-800 bg-gray-900 px-4">
      <div className="h-full flex items-center justify-between gap-3">
        <NavLink to="/" onClick={closeMenu} className="flex min-w-0 items-center gap-2">
          <span className="text-lg font-bold tracking-tight text-white">OSAF</span>
          <span className="hidden text-xs text-gray-500 sm:inline">Open Shark Attack File</span>
        </NavLink>

        <nav className="hidden items-center gap-1 md:flex" aria-label="Primary navigation">
          {links}
          <span className="mx-1 h-5 w-px bg-gray-700" />
          {isAuthenticated ? (
            <div className="flex items-center gap-2">
              <span className="max-w-36 truncate text-xs text-gray-500">{user.username}</span>
              <button
                onClick={logout}
                className="rounded-md px-2 py-2 text-xs text-gray-400 hover:bg-gray-800/60 hover:text-white"
              >
                Sign out
              </button>
            </div>
          ) : (
            <NavLink to="/login" className={navLinkClass}>Sign in</NavLink>
          )}
        </nav>

        <button
          type="button"
          onClick={() => setMenuOpen((open) => !open)}
          className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-gray-700 text-gray-300 hover:bg-gray-800 hover:text-white md:hidden"
          aria-expanded={menuOpen}
          aria-controls="mobile-navigation"
          aria-label={menuOpen ? "Close navigation" : "Open navigation"}
        >
          {menuOpen ? (
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeWidth="2" d="M6 6l12 12M18 6 6 18" />
            </svg>
          ) : (
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeWidth="2" d="M4 7h16M4 12h16M4 17h16" />
            </svg>
          )}
        </button>
      </div>

      {menuOpen && (
        <nav
          id="mobile-navigation"
          className="absolute inset-x-0 top-full grid grid-cols-2 gap-1 border-b border-gray-700 bg-gray-900 p-3 shadow-2xl md:hidden"
          aria-label="Mobile navigation"
        >
          {links}
          <div className="col-span-2 mt-1 border-t border-gray-800 pt-2">
            {isAuthenticated ? (
              <div className="flex items-center justify-between gap-3 px-2">
                <span className="truncate text-xs text-gray-500">Signed in as {user.username}</span>
                <button
                  onClick={() => {
                    closeMenu();
                    logout();
                  }}
                  className="rounded-md px-3 py-2 text-sm text-gray-300 hover:bg-gray-800"
                >
                  Sign out
                </button>
              </div>
            ) : (
              <NavLink to="/login" onClick={closeMenu} className={navLinkClass}>Sign in</NavLink>
            )}
          </div>
        </nav>
      )}
    </header>
  );
}
