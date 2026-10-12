import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "../api/client";
import { cityName, countryName, daysAgo, formatDate } from "../format";

export default function DataQualityPage() {
  const { data, isPending, error } = useQuery({
    queryKey: ["data-quality"],
    queryFn: () => unwrap(api.GET("/api/v1/data-quality")),
  });

  if (isPending) {
    return <p className="updating">טוען...</p>;
  }
  if (error) {
    return <p className="error">לא הצלחנו לטעון את דוח איכות הנתונים: {error.message}</p>;
  }

  return (
    <section className="card">
      <h1>איכות הנתונים וכיסוי</h1>
      <p className="note">כמה נתונים יש לנו על כל יעד. מקף פירושו שאין נתון: אנחנו מציגים את החוסרים, לא מסתירים אותם.</p>

      <h2>כיסוי לפי יעד</h2>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>עיר</th>
              <th>מדינה</th>
              <th>תצפיות טיסה</th>
              <th>מלונות בחיפוש</th>
              <th>מחיר המלון עודכן</th>
            </tr>
          </thead>
          <tbody>
            {data.coverage.map((row) => (
              <tr key={`${row.city_name}-${row.country_name}`}>
                <td>{cityName(row)}</td>
                <td>{countryName(row)}</td>
                <td>{row.flight_obs_count}</td>
                <td>{row.hotel_sample_size ?? "-"}</td>
                <td>{daysAgo(row.hotel_price_age_days)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2>נפח האיסוף לפי יום</h2>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>יום</th>
              <th>נאספו</th>
              <th>מחיפושי משתמשים</th>
            </tr>
          </thead>
          <tbody>
            {data.collection_volume.map((row) => (
              <tr key={row.day}>
                <td>{formatDate(row.day)}</td>
                <td>{row.observations_collected}</td>
                <td>{row.observations_from_searches}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
