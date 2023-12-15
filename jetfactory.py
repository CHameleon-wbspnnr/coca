#!/usr/bin/env python
from argparse import ArgumentParser
from contextlib import contextmanager
from datetime import datetime
import json
import fnmatch
from sh import debootstrap, zerofree, split, mount, umount, du, mkfs, fallocate, parted, cp
from shutil import rmtree, copy
from patoolib import extract_archive, create_archive
from subprocess import Popen
from sys import stdout, stderr
import os
from requests import get, head
from clint.textui import progress
from glob import glob
import gi
gi.require_version('Guestfs', '1.0')
from gi.repository import Guestfs

#
# Global variables
#

cur_date = datetime.today().strftime('%Y-%m-%d')
image_ext = ['.img', '.qcow2', '.raw']
archive_ext = ['.tar.gz', '.bz2', '.tbz2', '.xz', '.tar', '.tar.xz', '.7z']

#
# Utilities
#

def wget(url, outdir = None):
    ''' File download with progress helper '''
    if outdir is not None:
        fetched = outdir + os.path.basename(url)
    else:
        fetched = os.path.basename(url)

    req = head(url, allow_redirects=True)
    size = int(req.headers.get('content-length', -1))

    res = get(url, allow_redirects=True, stream=True)
    if (not os.path.exists(fetched) \
    and not os.path.exists(os.path.splitext(fetched)[0])) \
    or not os.path.getsize(fetched) == size:
        print("\nDownloading rootfs image: {} \
            of size: {}MiB".format(fetched, size * 1048576))
        with open(fetched, 'wb') as fd:
            for chunk in progress.bar(res.iter_content(chunk_size=1024),
            expected_size=(size/1024) + 1): 
                if chunk:
                    fd.write(chunk)
                    fd.flush()
    return fetched


#
# LinuxFactory
#

class LinuxFactory:
    def __init__(self, device, distribution):
        ''' Class constructor '''
        self.device = device
        self.name = distribution
        
        # Some distributions put guestfs in /usr/share
        if os.path.exists("/usr/share/guestfs/appliance"):
            os.environ['LIBGUESTFS_PATH'] = "/usr/share/guestfs/appliance"

    def __del__(self):
        ''' Class destructor '''
        rmtree(self.distro_dir, ignore_errors=True)

    def _run(self, cmd):
        ''' subprocess.Popen wrapper '''
        out, err = Popen(cmd, universal_newlines=True,
            shell=True, stdout=stdout,stderr=stderr).communicate()
        if err is not None:
            raise Exception(err)
        return out

    def _extract(self, fd, out):
        ''' Rootfs extract helper '''
        if fd.endswith(tuple(archive_ext)):
            extract_archive(fd, outdir=out)
        
        elif fd.endswith(tuple(image_ext)):
            g = Guestfs.Session()
            g.add_drive_ro(fd)
            g.launch()
            root = g.inspect_os()
            assert(len(root) == 1)
            g.mount(root[0], "/")
            print("\nFound root at {}. Extracting / from disk image {}."
                .format(root[0], fd))
            g.copy_out("/", out)
            g.umount("/")
        
        else:
            raise Exception("\nERROR: Unsupported file format for {}".format(fd))

        print("Extracted {} successfully".format(fd))

    def prepare(self):
        ''' Create build directories '''

        print("Preparing build environment")

        # Build dir
        self.build_dir = os.getcwd() + "/linux/"

        # Download dir, used to store base image
        self.dl_dir = self.build_dir + "downloadedFiles/"

        # Distro dir, used for chroot and creating distro
        self.distro_dir = self.build_dir + self.device + "-" + self.name + "/"

        # Chroot dir
        self.chroot_dir = self.distro_dir + "." + self.name
        
        # Disk image name
        self.disk_name = self.distro_dir + self.name + "-" + cur_date + ".img"

        # Zip name
        self.zip_name = self.build_dir + self.name + "-" + cur_date + ".7z"

        # Remove old zip
        if os.path.exists(self.zip_name):
            os.remove(self.zip_name)
        
        # Remove old chroot dir
        if os.path.exists(self.distro_dir):
            rmtree(self.distro_dir)

        # Create the chroot dir
        os.makedirs(self.chroot_dir, exist_ok=True)

        # Create download dir
        os.makedirs(self.dl_dir, exist_ok=True)

        # Create hekate folders
        if self.device == "icosa":
            os.makedirs(self.distro_dir + "/switchroot/install/", exist_ok=True)

    def parseJson(self):
        ''' JSON parser '''

        print("Parsing JSON template")

        # Set config dir path
        self.configdir = os.path.dirname(__file__) \
            + "/configs/" + self.name + ".json"

        # Initialize script empty array
        self.script = []

        # Load JSON relatively to current script file to retrieve variables
        with open(self.configdir) as js:
            parsed = json.load(js)

        # Error check build method
        if "url" in parsed:
            self.url = parsed["url"]

        elif "debootstrap" in parsed:
            self.debootstrap = parsed["debootstrap"]
        
        else:
            raise Exception("\nNo URL found for {} configuration."
            .format(self.name))

        # Error check chroot script
        if "script" not in parsed:
            print("\nNo chroot script found for {} configuration."
            .format(self.name))
            parsed["script"] = ""
        
        # Pre run script
        if "pre" in parsed:
            for i in range(len(parsed["pre"])):
                config = os.path.dirname(__file__) \
                    + "/configs/common/" + parsed["pre"][i] + ".json"
                
                with open(config) as js:
                    self.script += json.load(js)["script"]
        
        # Chroot script
        self.script += parsed["script"]

        # Post run script
        if "post" in parsed:
            for i in range(len(parsed["post"])):
                config = os.path.dirname(__file__) \
                    + "/configs/common/" + parsed["post"][i] + ".json"

                with open(config) as js:
                    self.script += json.load(js)["script"]

        # Cache dir
        if "cache" in parsed:
            self.cache = parsed["cache"]
            self.cachedir = self.build_dir + ".cache" + self.cache
            os.makedirs(self.cachedir, exist_ok=True)

    def _extract_rootfs(self, rootfs):
        ''' Image or archive extraction helper '''
        extracted_image = self.dl_dir + os.path.basename(os.path.splitext(rootfs)[0])

        for arch in archive_ext:
            for img in image_ext:
                if rootfs.endswith(img + arch):
                    print("\nFound compressed disk image {}".format(rootfs))
                    if not os.path.exists(extracted_image):
                        self._extract(rootfs, self.dl_dir)
                    self._extract(extracted_image, self.chroot_dir)
                    return

        if os.path.exists(extracted_image):
            self._extract(extracted_image, self.chroot_dir)

        else:
            self._extract(rootfs, self.chroot_dir)

    @contextmanager
    def chroot(self, root):
        # Keep a reference to real root
        real_root = os.open("/", os.O_RDONLY)

        print("\nChrooting in {}\n".format(root))
        try:
            # Unlink resolv.conf if it is a symlink
            if os.path.islink(root + "/etc/resolv.conf"):
                os.unlink(root + "/etc/resolv.conf")

            # Copy host resolv.conf
            copy("/etc/resolv.conf", root + "/etc/resolv.conf")

            # Mount the needed dirs for chroot
            for mnt in ('/proc', '/dev', '/sys'):
                chroot_mnt = root + mnt
                if not os.path.ismount(chroot_mnt):
                    if not os.path.isdir(chroot_mnt):
                        os.makedirs(chroot_mnt)
                    mount(mnt, chroot_mnt, "--rbind")

            # Mount cache separately
            if hasattr(self, "cache"):
                os.makedirs(root + self.cache, exist_ok=True)
                mount(self.cachedir, root + self.cache, "--rbind")

            # Set GID 0 = root
            os.setgid(0)
            
            # Set UID 0 = root
            os.setuid(0)
            
            # Chroot to new root
            os.chroot(root)
            
            # Chdir to /
            os.chdir('/')
            
            # Block until all commands are done
            yield

        except:
            # Return to real root
            os.fchdir(real_root)
            
            # Return to current dir
            os.chroot(".")
            
            # Close real root fd
            os.close(real_root)

            for mnt in ('/proc', '/dev', '/sys'):
                chroot_mnt = root + mnt
                if os.path.ismount(chroot_mnt):
                    print("Unmounting {}".format(chroot_mnt))
                    umount("-lf", chroot_mnt)

        finally:
            # Return to real root
            os.fchdir(real_root)
            
            # Return to current dir
            os.chroot(".")
            
            # Close real root fd
            os.close(real_root)

            for mnt in ('/proc', '/dev', '/sys'):
                chroot_mnt = root + mnt
                if os.path.ismount(chroot_mnt):
                    print("Unmounting {}".format(chroot_mnt))
                    umount("-lf", chroot_mnt)

        print("\nChroot install successful !")

    def makeDistribution(self):
        ''' Create distribution based on configs '''
        print("\nMaking distribution")

        if not hasattr(self, "debootstrap"):
            path = wget(self.url, self.dl_dir)
            self._extract_rootfs(path)
        else:
            print("\nDebootstraping {} for {}. This will take a while..."
                .format(self.name, self.debootstrap[0]))

            debootstrap(
                "--include=wget,gnupg",
                "--arch=" + self.debootstrap[0],
                self.name,
                self.chroot_dir,
                self.debootstrap[1]
            )

        # Actuall chroot process
        with self.chroot(self.chroot_dir):
            for cmd in self.script:
                self._run(cmd)

    def makeDiskImage(self):
        ''' EXT4 disk image creation '''
        print("\nCreating disk image {}. This will take a while."
            .format(self.disk_name))

        # Get size in MB and add an extra 768MB
        size = str(int(du(
                        "-sh",
                        "-BM",
                        self.chroot_dir
                        ).split()[0][0:-1]) + 2048)

        # Create disk image with size
        fallocate("-l", size + "M", self.disk_name)

        # Create partition using parted
        parted(
                "-a",
                "optimal",
                "--script",
                self.disk_name,
                "mklabel",
                "msdos",
                "mkpart",
                "primary",
                "ext4",
                "0%",
                "100%"
        )

        # Create ext4 fs on image with switchroot label
        mkfs(
                "-F",
                "-t",
                "ext4",
                "-L",
                "SWR-" + self.name[0:3].upper(),
                self.disk_name
            )

        # Copy chroot_dir to image mountpoint
        mount("-o", "loop", self.disk_name, "/mnt")

        for dn in glob(self.chroot_dir + "/*"):
            cp("-rp", dn, "/mnt")

        umount("/mnt")

        print("\nRunning zerofree on disk image")
        zerofree(self.disk_name)

    def makeHekateZip(self):
        ''' Create a 7z archive containing a splitted image file to fit on fat32 '''
        # Check if image needs alignement
        size = os.path.getsize(self.disk_name)
        aligned_size = (size + (4194304-1)) & ~(4194304-1)
        aligned_check = aligned_size - size

        if aligned_check != 0:
            print("\nAligning by adding {} bytes: ".format(str(aligned_check)))
            self._run("dd if=/dev/zero bs=1 count=" + str(aligned_check) + " >> " + self.disk_name)

        print("\nSpliting {} into chunks".format(self.disk_name))
        split("-b4290772992", "--numeric-suffixes=0", self.disk_name, self.distro_dir + "/switchroot/install/" + "l4t.")

        print("Creating hekate compatible 7zip")
        create_archive(self.zip_name, [self.distro_dir + "/switchroot/"])

    def main(self):
        ''' Create distribution disk image '''

        self.prepare()
        self.parseJson()
        self.makeDistribution()
        self.makeDiskImage()

        if self.device == "icosa":
            self.makeHekateZip()
        else:
            create_archive(self.zip_name, [self.disk_name])

        print("\nDistribution creation done ! You can find the file in {}"
            .format(self.zip_name))

if __name__ == '__main__':
    # Initialise argument parser
    parser = ArgumentParser()

    # Add arguments to parser
    parser.add_argument(
        "-b", "--build", dest="build", nargs='+',
        help="-b, --build [DEVICE] [DISTRIBUTION], \
        Build a DISTRIBUTION set in DEVICE json")

    parser.add_argument(
        "-c", "--clean", dest="clean",
        action='store_true', help="-c, --clean, Clean cache")

    # Parse arguments
    args = parser.parse_args()
 
    # Pass parser to main and call it
    try:
        if args.clean is True:
            if os.path.exists(os.getcwd() + "/linux/.cache"):
                print("Cleaning cache directory")
                os.removedirs(os.getcwd() + "/linux/.cache")

        if args.build is not None:
            LinuxFactory(
                args.build[0],
                args.build[1]
            ).main()
    except AttributeError:
        parser.print_help()
        parser.exit()
