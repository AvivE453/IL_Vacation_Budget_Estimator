import { Link } from "react-router";

export default function NotFoundPage() {
  return (
    <div className="card">
      <h1>הדף לא נמצא</h1>
      <p>
        <Link to="/">חזרה לחיפוש</Link>
      </p>
    </div>
  );
}
