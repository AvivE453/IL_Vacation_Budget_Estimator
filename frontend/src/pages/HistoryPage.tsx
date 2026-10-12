import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import { api, unwrap } from "../api/client";
import { dateTime, formatDate, money, TIER_NAMES } from "../format";

export default function HistoryPage() {
  const { data, isPending, error } = useQuery({
    queryKey: ["searches"],
    queryFn: () => unwrap(api.GET("/api/v1/searches")),
  });

  if (isPending) {
    return <p className="updating">טוען...</p>;
  }
  if (error) {
    return <p className="error">לא הצלחנו לטעון את החיפושים שלך: {error.message}</p>;
  }

  return (
    <section className="card">
      <h1>החיפושים שלי</h1>
      {data.length > 0 && <p className="note">לחצו על המספר כדי לראות את החיפוש.</p>}
      {data.length === 0 ? (
        <p>
          עוד לא חיפשת מהדפדפן הזה. <Link to="/">לחיפוש ראשון</Link>
        </p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>יציאה מ-</th>
                <th>תאריך יציאה</th>
                <th>תאריך חזרה</th>
                <th>תקציב</th>
                <th>מלון</th>
                <th>מתי חיפשת</th>
              </tr>
            </thead>
            <tbody>
              {data.map((search, index) => (
                <tr key={search.search_id}>
                  {/* Numbered per browser, oldest = 1, rather than by the global id. */}
                  <td>
                    <Link to={`/history/${search.search_id}`}>{data.length - index}</Link>
                  </td>
                  <td>{search.origin_iata}</td>
                  <td>{formatDate(search.depart_date)}</td>
                  <td>{formatDate(search.return_date)}</td>
                  <td>{money(search.budget_amount, search.budget_currency)}</td>
                  <td>{TIER_NAMES[search.hotel_tier]}</td>
                  <td>{dateTime(search.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
