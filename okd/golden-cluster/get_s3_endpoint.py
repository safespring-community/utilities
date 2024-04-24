import openstack
conn = openstack.connect()
print(conn.endpoint_for('s3'))
