import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { api, ApiError, unwrap } from "../api/client";
import { cityName, formatDate, money, TIER_NAMES } from "../format";

export default function SavedSearchPage() {
  // The :searchId part of /history/:searchId - always a string from the URL.
  const searchId = Number(useParams().searchId);

  const { data, isPending, error } = useQuery({
    queryKey: ["searches", searchId],
    queryFn: () => unwrap(api.GET("/api/v1/searches/{search_id}", { params: { path: { search_id: searchId } } })),
    enabled: Number.isInteger(searchId),
  });

  // Not a number (/history/abc), or no such search in this browser's history.
  const notFound = !Number.isInteger(searchId) || (error instanceof ApiError && error.status === 404);
  if (notFound) {
    return (
      <div className="card">
        <h1>החיפוש לא נמצא</h1>
        <p>
          הוא לא קיים, או שנעשה מדפדפן אחר. <Link to="/history">לחיפושים שלי</Link>
        </p>
      </div>
    );
  }
  if (isPending) {
    return <p className="updating">טוען...</p>;
  }
  if (error) {
    return <p className="error">לא הצלחנו לטעון את החיפוש: {error.message}</p>;
  }

  return (
    <section className="card">
      <h1>
        {data.origin_iata}, {formatDate(data.depart_date)} – {formatDate(data.return_date)}
      </h1>
      <p className="note">
        תקציב {money(data.budget_amount, data.budget_currency)}, מלון {TIER_NAMES[data.hotel_tier]}
      </p>
      {data.exact_dates_only !== null && (
        <p className="note">
          {data.exact_dates_only
            ? "ההערכות האלה התבססו על טיסות בתאריכים המדויקים."
            : "ההערכות האלה התבססו על התאריכים הקרובים ביותר, לא על התאריכים המדויקים."}
        </p>
      )}

      {data.results.length === 0 ? (
        <p>כל היעדים היו מעל התקציב בחיפוש הזה, ולכן לא נשמר דירוג.</p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>מקום</th>
                <th>יעד</th>
                <th>חברה</th>
                <th>מלון</th>
                <th>סך הכול</th>
                <th>בתקציב?</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((result) => (
                <tr key={result.destination_id}>
                  <td>{result.cost_rank}</td>
                  <td>{cityName(result)}</td>
                  <td>{result.airline_name ?? result.airline_code ?? "-"}</td>
                  <td>{TIER_NAMES[data.hotel_tier]}</td>
                  <td className="total">{money(result.estimated_total_amount, data.currency)}</td>
                  <td>
                    <span className={result.within_budget ? "tag tag-yes" : "tag tag-no"}>
                      {result.within_budget ? "כן" : "לא"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
