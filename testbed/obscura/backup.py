# Root maintenance job (run via sudo runjob.sh). Loads the job spec from jobs.yml.
import yaml
data = yaml.load(open("/opt/app/jobs.yml"), Loader=yaml.Loader)  # unsafe: executes YAML tags
print("loaded job:", data)
