# Import iTunes Playlists Onto Your Plex Server

This standalone utility takes playlists that are exported from iTunes in *.m3u format and using that, creates a copy of the playlist on your Plex server.

## Description

A couple of key concepts to facilitate success:

The music library on your Plex server should contain all of your iTunes music in the standard artist/album/song format.  Copying your entire iTunes music folder over to Plex works best by ensuring all the songs in your playlist are present on your server.

Each playlist you wish to transfer needs to be exported from iTunes as a .m3u file.  I recommend creating a Playlist Export folder in your iTunes folder: c:\Users\USERNAME\Music\iTunes\Playlist Export to hold your exported playlists.  To export a playlist in iTunes, select the playlist then click File>Library>Export Playlist and save your playlist in the Playlist Export folder you created above.  Repeat to export all desired playlists.

I assume your Plex is located on your local network, and it is accessible using http.  This utility does not support https access of your server.

The utility has three tabs:

The first is where you access your server.  There are two different methodologies to do this and neither is preferable over the other.

The first methodology requests an access token from the Plex.tv website using your Plex username and password.  It then uses this token to get information about your server from Plex.tv.  The key information is a list of local ip addresses that your server has used in the past.  The utility then iterates through this list attempting to find your server on your local network.

The second methodology requires you to access your plex server and copy the local ip address and access token into the utility.  How to do this is explained in the utility.

Once you have access there are two other tabs.  One tab is used to access your saved *.m3u files and transfer them over to your server.  The second is a list of general information about your server that you may find informative.  This tabs does have a button to count the number of photos in your Pictures library.  This has nothing to do with exporting playlists and is just information for the curious as Plex counts Picture folders and not the pictures themselves.

The first time you attempt to transfer a playlist, the utility creates a simple database of your music library.  Depending on how many songs you have, this may take some time.  You should delete this database every time you add new songs to your Plex server.

There is a status console at the bottom of each tab that provides useful feedback on the process.

## Getting Started

The easiest way to get started is to download the itunestoplex.exe executable and run it.  It can be stored on any directory folder you prefer.  The source code was created and compiled using the PyCharms IDE.

### Dependencies

This program was built and tested on a Windows 11 PC and assumes you have the latest version of Plex running on your server.  Other operating systems, i.e. Windows 10, or older versions of Plex have not been tested and there is no guarantee this utility will work.

## Author

Robert Suffern - @rcsuffern (X)


## Version History

* 1.0 Initial Release

## License

This project is licensed under the MIT License - see the LICENSE file for details.  This software is provided "as is" without warranty of any kind.