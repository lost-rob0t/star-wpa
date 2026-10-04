const assert = require('assert');
const vm = require('vm');
const views = require('../views/wireless.json').views;
const ns = 'org.starintel/wpa@1';
const event = {id: 'e1', dataset: 'lab', dtype: 'event', schemaVersion: '0.10.1', eventKind: 'wireless-sighting', observedAt: 123,
  extensions: {[ns]: {receiverId: 'r1', bssid: 'aa:bb:cc:dd:ee:ff', networkId: 'n1', latitude: 0, longitude: 0, distanceMeters: 10}}};
function rows(name, doc) {
  const output = [];
  const map = vm.runInNewContext('(' + views[name].map + ')', {emit: (key, value) => output.push(JSON.parse(JSON.stringify({key, value})))});
  map(doc);
  return output;
}
assert.deepStrictEqual(rows('trilateration_windows', event)[0].key, ['lab', 'n1', 12]);
assert.deepStrictEqual(rows('by_network_receiver_time', event)[0].key, ['lab', 'n1', 'r1', 123]);
assert.deepStrictEqual(rows('by_transmitter_time', event)[0].key, ['lab', 'aa:bb:cc:dd:ee:ff', 123, 'r1']);
for (const name of Object.keys(views)) {
  assert.deepStrictEqual(rows(name, {...event, schemaVersion: '0.9.0'}), []);
  assert.deepStrictEqual(rows(name, {...event, deleted: true}), []);
  assert.deepStrictEqual(rows(name, {...event, _id: '_design/wireless'}), []);
}
assert.deepStrictEqual(rows('trilateration_windows', {...event, extensions: {[ns]: {...event.extensions[ns], latitude: NaN}}}), []);
assert.deepStrictEqual(rows('trilateration_windows', {...event, observedAt: -1}), []);
assert.deepStrictEqual(rows('by_geo_bucket', {id: 'p1', dtype: 'geo-point', dataset: 'lab', schemaVersion: '0.10.1', geometryType: 'point', latitude: '0.0001', longitude: '-0.0001'})[0].key, ['lab', 0, -1]);
assert.deepStrictEqual(rows('by_geo_bucket', {id: 'p1', dtype: 'geo-point', dataset: 'lab', schemaVersion: '0.10.1', geometryType: 'point', latitude: '', longitude: '0'}), []);
console.log('STAR-WPA-VIEWS-OK');
