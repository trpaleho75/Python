# LDAP request module

# Imports - 3rd party
import ldap3
from ldap3 import Server, Connection, ALL, NTLM
	
	
def ldap3Query(auth: dict, ldapServer: str, baseDn: str, upn: str) -> str:
	server = ldap3.Server(ldapServer)
	with ldap3.Connection(server, 
							user = auth['username'], 
							password = auth['password'], 
							authentication = 'NTLM') as conn:
								conn.search(search_base = baseDn,
											search_filter = '(userPrincipalName=' + upn + ')',
											attributes = ['sAMAccountName'])
								result = conn.entries[0]
								return str(result.sAMAccountName)