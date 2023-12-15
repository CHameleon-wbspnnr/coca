FROM ubuntu:21.04

ARG DEBIAN_FRONTEND=noninteractive
RUN apt update -y && apt-get install -y gnupg2 && \
	apt install -y \
		qemu \
		qemu-user-static \
		binfmt-support \
		p7zip-full \
		util-linux \
		zerofree \
		git \
		unrar \
		unzip \
		python3 \
		python3-pip \
		libguestfs-tools \
		libguestfs-dev \
		libguestfs-gobject-dev \
		libguestfs-gobject-1.0-0 \
		xz-utils \
		build-essential \
		linux-image-generic \
	&& rm -rf /var/lib/apt/lists/*

WORKDIR /build
VOLUME /build

COPY . /jet
ENV PATH=/root/.local/bin:$PATH
RUN pip3 install --user -e /jet/

ENTRYPOINT ["python3", "/jet/jetfactory.py"]
CMD [""]
