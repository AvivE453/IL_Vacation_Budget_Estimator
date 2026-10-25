// CloudFront Function on the site's S3 behavior (not /api/*). Refreshing an
// inner page such as /history/5 asks S3 for a file that doesn't exist; a path
// whose last segment has no file extension gets the React app's index.html,
// and React Router shows the page. Not CloudFront's custom error responses:
// those would also turn a real API 404 into index.html.
function handler(event) {
  var request = event.request;
  var lastSegment = request.uri.split("/").pop();
  if (!lastSegment.includes(".")) {
    request.uri = "/index.html";
  }
  return request;
}
