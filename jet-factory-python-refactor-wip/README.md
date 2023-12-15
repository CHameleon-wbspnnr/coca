# Jet Factory

Create live and flashable linux distribution root filesystem images for L4T.

## Usage

```txt
usage:
  -b, --build <device> <distribution>	build a distribution based on <device> directory in "configs/<device>"
					and <distribution> found in "configs/<device>/<distribution>"
  -c, --cache				clean cache directory
  -h, --help            		show this help message and exit
```

## Build example

For fedora on icosa device:
```sh
sudo docker run --privileged --rm -it -v "$PWD"/linux:/build/linux registry.gitlab.com/switchroot/gnu-linux/jet-factory:python-refactor-wip -b icosa fedora
```

## Credits

### Special mentions

@gavin_darkglider, @CTCaer, @ByLaws, @ave and all the L4S & [switchroot](https://switchroot.org) members \
For their various work and contributions to switchroot.

### Contributors

@Stary2001, @Kitsumi, @parkerlreed, @AD2076, @PabloZaiden, @andrebraga1 \
@nicman23 @Matthew-Beckett @Nautilus @3l_H4ck3r_C0mf0r7
For their work, support and direct contribution to this project.
