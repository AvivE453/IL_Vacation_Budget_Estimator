import { NavLink, Outlet } from "react-router";

// The frame every page shares: the title and the menu stay, and <Outlet />
// is replaced by the page that matches the URL.
export default function Layout() {
  return (
    <>
      <header>
        <h1>IL Vacation Budget Estimator</h1>
        <nav>
          <NavLink to="/" end>
            Search
          </NavLink>{" "}
          | <NavLink to="/history">History</NavLink> |{" "}
          <NavLink to="/data-quality">Data quality</NavLink>
        </nav>
      </header>
      <main>
        <Outlet />
      </main>
    </>
  );
}
