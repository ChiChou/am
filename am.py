import csv
import json
import zipfile

from typing import Dict
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
from dateutil import tz

from api import artwork, lookup, song_info

SKIP_FACTOR = 0.3
THIS_YEAR = datetime.now().year


class Track:
    amid: int
    artist: str
    title: str
    genre: str
    year: int


class Processor:
    ignore_list: set
    library: Dict[str, Track]

    def __init__(self, cwd: Path, year: int, output=None, tz=None):
        self.cwd = cwd / 'Apple Music Activity'
        self.year = year if type(year) is int else THIS_YEAR
        self.str_year = str(self.year)
        self.output = output if isinstance(output, Path) else cwd / 'output'
        self.tz = tz

        if self.output.exists():
            if not self.output.is_dir():
                raise IOError('Output %s and it\'s not a folder' % self.output)
        else:
            self.output.mkdir(parents=True)

        self.load_library()
        self.load_ignore()

    def load_ignore(self):
        self.ignore_list = set()
        txt = Path(__file__).parent / 'ignore.txt'
        if not txt.is_file():
            return

        with txt.open('r', encoding='utf8') as fp:
            for line in fp:
                name = line.strip()
                if len(name):
                    self.ignore_list.add(name)

    def load_library(self):
        self.library = {}
        tracks_zip = self.cwd / 'Apple Music Library Tracks.json.zip'
        with zipfile.ZipFile(tracks_zip) as zf:
            data = json.load(zf.open('Apple Music Library Tracks.json'))

        assert(len(data) > 0)

        for row in data:
            amid = row.get('Apple Music Track Identifier')

            if not amid:
                continue

            track = Track()
            track.amid = int(amid)
            track.artist = row.get('Artist')
            track.title = row.get('Title')
            track.genre = row.get('Genre')
            track.year = int(row.get('Track Year'))

            self.library[amid] = track

    def daily_tracks(self):
        filename = self.cwd / 'Apple Music - Play History Daily Tracks.csv'
        counter_song = Counter()
        counter_genre = Counter()
        counter_month = Counter()
        descriptions = {}

        with open(filename, encoding='utf8') as fp:
            reader = csv.reader(fp, quotechar='"')
            header = next(reader)

            id_index = header.index('Track Identifier')
            desc_index = header.index('Track Description')
            date_index = header.index('Date Played')
            skip_index = header.index('Skip Count')
            play_index = header.index('Play Count')
            duration_index = header.index('Play Duration Milliseconds')
            end_reason_index = header.index('End Reason Type')

            for row in reader:
                desc = row[desc_index]
                date = row[date_index]
                amid = int(row[id_index])
                duration = int(row[duration_index])
                end_reason = row[end_reason_index]

                mo = int(date[4:6])
                counter_month[mo] += duration

                # you skipped the track explicitly
                weight = SKIP_FACTOR
                if end_reason == 'TRACK_SKIPPED_FORWARDS':
                    weight * 1.6

                if not date.startswith(self.str_year):
                    continue

                # simple formula
                point = (int(row[play_index]) -
                         int(row[skip_index]) * weight)
                counter_song[amid] += point
                descriptions[amid] = desc

                if amid in self.library:
                    genre = self.library.get(amid).genre
                    counter_genre[genre] += duration

        top10 = sorted(
            counter_song.items(), key=lambda x: x[1], reverse=True)[0:10]
        songs = [amid for amid, points in top10]
        data = lookup(map(str, songs))

        assert(data['resultCount'] == 10)
        with open(self.output / 'songs.json', 'w', encoding='utf8') as fp:
            json.dump(data['results'], fp, indent=2)

        with open(self.output / 'genre.json', 'w', encoding='utf8') as fp:
            json.dump(counter_genre, fp, indent=2)

        with open(self.output / 'monthly.json', 'w', encoding='utf8') as fp:
            json.dump(counter_month, fp, indent=2)

    def local_time(self, t: datetime):
        return t.replace(tzinfo=timezone.utc).astimezone(tz=self.tz)

    def activities(self):
        filename = self.cwd / 'Apple Music Play Activity.csv'
        counter_artists = Counter()
        # counter_songs = Counter()
        counter_month = Counter()
        counter_hour = [0] * 24

        late_night = 0
        late_night_track: dict = None

        possible_fmt = (
            '%Y-%m-%dT%H:%M:%S.%fZ',
            '%Y-%m-%dT%H:%M:%SZ'
        )

        with open(filename, 'r', encoding='utf8') as fp:
            reader = csv.reader(fp, quotechar='"', quoting=csv.QUOTE_MINIMAL)
            header = next(reader)

            time_index = header.index('Event Received Timestamp')
            duration_index = header.index('Play Duration Milliseconds')
            artist_index = header.index('Artist Name')
            song_index = header.index('Song Name')

            for row in reader:
                try:
                    duration = int(row[duration_index])
                except ValueError:
                    continue

                if duration <= 0:
                    continue

                for fmt in possible_fmt:
                    try:
                        t = datetime.strptime(row[time_index], fmt)
                        break
                    except ValueError:
                        continue
                else:
                    raise ValueError('Unable to parse time %s' %
                                     row[time_index])

                t = self.local_time(t)
                if t.year != self.year:
                    continue

                counter_hour[t.hour] += duration
                counter_month[t.month] += duration

                artist = row[artist_index]
                if artist in self.ignore_list:
                    continue

                if 'Tyler, The Creator' == artist:  # Well
                    artists = [artist]
                else:
                    artists = artist.split(', ')
                for person in artists:
                    if not person:
                        continue
                    counter_artists[person] += duration
                song = row[song_index]
                # counter_songs[song] += duration

                if t.hour < 6:
                    s = t.hour * 3600 + t.minute * 60 + t.second
                    if s >= late_night:
                        late_night = s
                        late_night_track = {
                            'timestamp': t.timestamp() * 1000,
                            'localtime': str(t),
                            'title': song,
                            'artist': artist,
                        }

        mapping = {
            'artists': counter_artists,
            # 'songs': counter_songs,
        }

        with open(self.output / 'sleepless.json', 'w', encoding='utf8') as fp:
            title = '%s - %s' % (late_night_track['artist'],
                                 late_night_track['title'])
            late_night_track['artwork'] = artwork(title, 600)
            json.dump(late_night_track, fp, indent=2)

        with open(self.output / 'hourly.json', 'w', encoding='utf8') as fp:
            json.dump(counter_hour, fp, indent=2)

        for k, v in mapping.items():
            del v['']
            max_count = max(v.values())
            normalized = [[item, count * 100 / max_count]
                          for item, count in v.items()]
            top = sorted(normalized, key=lambda x: x[1], reverse=True)

            with open(self.output / ('%s.json' % k), 'w', encoding='utf8') as fp:
                json.dump(top, fp, indent=2)

    def aggregate(self):
        self.daily_tracks()
        self.activities()


if __name__ == '__main__':
    import argparse

    def type_path(p):
        return Path(p).absolute()

    def type_tz(z):
        return tz.gettz(z)

    parser = argparse.ArgumentParser(
        description='Visualize your Apple Music data')
    parser.add_argument('-t', '--tz',
                        type=type_tz,
                        default=None,
                        dest='tz',
                        help='Set timezone of the data (Default: local timezone)')
    parser.add_argument('-y', '--year', dest='year', metavar='N',
                        type=int, nargs='+',
                        help='Year (Default: current year)')
    parser.add_argument(
        '-d',
        '--dir',
        type=type_path,
        default=Path(__file__).absolute().parent.parent,
        help="Path to the data directory")
    parser.add_argument(
        '-o',
        '--output',
        type=type_path,
        default=Path(__file__).parent / 'web' / 'data',
        help="Output path")
    args = parser.parse_args()

    proc = Processor(args.dir, year=args.year, output=args.output, tz=args.tz)
    proc.aggregate()
