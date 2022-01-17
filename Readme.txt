pip install python-telegram-bot --upgrade

/Applications/Python\ 3.7/Install\ Certificates.command

FROM python:3.10.1-bullseye

docker run -d -P --name <name of your container> -v /path/to/local/directory:/path/to/container/directory <image name> ...


require 'pathname'
Pathname.glob('/path_to_file_directory/*.eml').each do |p|
    p.rename p.sub_ext(".html")
end
