import { Link, NavLink, Outlet } from "react-router";

// The frame every page shares: the header stays, and <Outlet /> is replaced
// by the page that matches the URL.
export default function Layout() {
  return (
    <>
      <header className="site-header">
        <div className="site-header-inner">
          <Link to="/" className="brand">
            חופשה <span>לפי תקציב</span>
          </Link>
          <nav>
            <NavLink to="/" end>
              חיפוש
            </NavLink>
            <NavLink to="/history">החיפושים שלי</NavLink>
            <NavLink to="/data-quality">איכות הנתונים</NavLink>
          </nav>
        </div>
      </header>
      <main>
        <Outlet />
      </main>
    </>
  );
}
