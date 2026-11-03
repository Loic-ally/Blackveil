import yaml
data = yaml.load(open("/opt/app/jobs.yml"), Loader=yaml.Loader)
print("loaded job:", data)
