sudo docker rm -f $(sudo docker ps -a -q --filter "ancestor=primos-checkins-backend:django")
sudo docker rmi primos-checkins-backend:django

sudo docker-compose build
sudo docker-compose run --rm app django-admin startproject core .
sudo docker-compose up
