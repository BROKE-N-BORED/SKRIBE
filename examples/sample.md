# How to back up a Linux home folder

This guide explains how to back up the home folder on a Linux computer using rsync. It is written for someone who has used a terminal a little but has never set up a backup before.

### Why back up

Computers fail. Drives die without warning, updates go wrong, and a single mistyped command can delete years of files. A backup is a copy of your files kept somewhere else, so one failure does not mean losing everything.

#### Picking a destination

Use an external drive or a second computer on the same network. Do not store the backup on the same drive as the original files. That defeats the purpose.

* Plug in the external drive and note where it mounts, usually under /media/yourname.
- Make a folder on it called backups.
* Check that the drive has more free space than your home folder uses.

### The backup command

Run this command to copy your home folder to the drive:

```
rsync -av --delete /home/yourname/ /media/yourname/drive/backups/home/
```

The -a flag keeps permissions and timestamps. The -v flag shows what is happening. The --delete flag removes files from the backup that you deleted at home, so the backup stays a true mirror.

1. Run the command once and watch for errors.
2. Run it again to confirm the second run is fast and copies almost nothing.
3. Check that a few files open correctly from the backup.

### Keeping it going

A backup you run once is better than none, but a backup you run every week is what actually saves you. Put the command in a weekly reminder, or add it to a cron job that runs on Sunday nights. Test restoring a file every few months. A backup you have never tested is a hope, not a backup.

If the drive fills up, the backup fails partway through and leaves a partial copy. Watch the free space and rotate to a fresh drive when the old one gets close to full. If rsync reports errors about permissions, check that you own the files you are copying.
