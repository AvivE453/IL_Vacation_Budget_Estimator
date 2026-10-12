import { Link } from "react-router";

export default function NotFoundPage() {
  return (
    <>
      <h2>Page not found</h2>
      <p>
        <Link to="/">Back to search</Link>
      </p>
    </>
  );
}
