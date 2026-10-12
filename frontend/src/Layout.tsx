import { NavLink, Outlet } from "react-router";

// The frame every page shares: the menu stays, and <Outlet /> is replaced by
// the page that matches the URL.
export default function Layout() {
  return (
    <>
      <nav>
        <NavLink to="/" end>
          Estimate
        </NavLink>
        <NavLink to="/history">History</NavLink>
        <NavLink to="/data-quality">Data Quality</NavLink>
      </nav>
      <main>
        <Outlet />
      </main>
    </>
  );
}
