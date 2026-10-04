function(doc) {
  if (!valid(doc) || doc.dtype !== 'geo-point' || doc.geometryType !== 'point') return;
  // Canonical decimal wire values are strings. Reject malformed values before numeric projection.
  if (!decimal(doc.latitude) || !decimal(doc.longitude)) return;
  var lat = Number(doc.latitude), lon = Number(doc.longitude);
  if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return;
  emit([doc.dataset, Math.floor(lat * 1000), Math.floor(lon * 1000)], doc.id);
}
