import com.onresolve.scriptrunner.runner.rest.common.CustomEndpointDelegate
import com.onresolve.scriptrunner.runner.customisers.WithPlugin;
import com.onresolve.scriptrunner.parameters.annotation.*
import com.atlassian.jira.component.ComponentAccessor;
import com.atlassian.jira.issue.MutableIssue;
import groovy.json.JsonSlurper;
import groovy.json.JsonException;
import groovy.json.JsonBuilder
import groovy.transform.BaseScript
import javax.ws.rs.core.MultivaluedMap
import javax.ws.rs.core.Response
import javax.ws.rs.core.Response.Status;
import javax.servlet.http.HttpServletRequest
@WithPlugin("com.okapya.jira.checklist")
import com.okapya.jira.customfields.*;

@BaseScript CustomEndpointDelegate delegate

def ChecklistItem createChecklistItem(ChecklistCFType cfType, String name, 
    boolean checked, String status, boolean mandatory, int rank) {
    def itemJson =  """
    {
        "name": "${name}",
        "checked": ${checked ? "true" : "false"},
        "statusId": "${status == null || status == "" ? "none" : status}",
        "mandatory": ${mandatory ? "true" : "false"},
        "rank": ${rank}
    }
    """;
    return cfType.getSingularObjectFromString(itemJson);
}

importChecklistItems(httpMethod: "POST", 
    groups: ["SDTEOB_ENVIRONMENT_ADMINS", "monarch_environment_admins"]) {
    MultivaluedMap queryParams, String body, HttpServletRequest request ->

    // The request variable is the user making the request. Done in case we 
    // want to do further checks on the user outside of being in a group
    def jsonSlurper = new JsonSlurper();
    def customFieldManager = ComponentAccessor.getCustomFieldManager();
    Map jsonRequest = null;
    
    log.warn("Begin Parse")
    try{
        //jsonRequest = jsonSlurper.parse(queryParams);
        jsonRequest = jsonSlurper.parseText(body) as Map;
    } catch(JsonException e){
        log.warn(e.toString())
        return Response.status(Status.BAD_REQUEST).build();
    } catch(Exception e){ //an error was thrown by the jsonSlurper that was not a JsonException
        log.warn("Error occured while parsing input")
        return Response.status(Status.INTERNAL_SERVER_ERROR).build();
    }
    int issueCount = 0;
   	
    log.warn("Parse Completed. Begin import")
    for(String issueKey : jsonRequest.keySet()){
        //log.warn(inputJson.get(issueKey).getClass());
        def fieldJsonObject = jsonRequest.get(issueKey) as Map;
        for(String customField : fieldJsonObject.keySet()){
            def checklistCustomField = customFieldManager.getCustomFieldObject(customField);
            def checklistCustomFieldType = (ChecklistCFType) checklistCustomField.getCustomFieldType();
            def ArrayList<ChecklistItem> newChecklistValue = new ArrayList<ChecklistItem>();
            //log.warn(fieldJsonObject.get(customField).getClass());  
            def fieldList = fieldJsonObject.get(customField) as ArrayList;
            for(int i =0; i< fieldList.size(); i++){
                def item = fieldList.get(i) as Map;
                String name = item.get("name");
                Boolean checked = Boolean.parseBoolean(item.get("checked") as String);
                Boolean mandatory = item.get("mandatory");
                int rank = item.get("rank");

                // Retrieve the Custom Field Type for the Checklist Custom Field
                // Create a new Checklist

                //log.warn(createChecklistItem(checklistCustomFieldType, name, checked, null, mandatory, rank));
                if(!name.isEmpty()){
                    newChecklistValue.add(createChecklistItem(checklistCustomFieldType, name, checked, null, mandatory, rank) );
                }

            }
            //Update the issue with the new checklist
            def issueManager = ComponentAccessor.getIssueManager();
            def issue = (MutableIssue) issueManager.getIssueByCurrentKey(issueKey);
            //def issue = (MutableIssue) issue;
            checklistCustomFieldType.updateValue(checklistCustomField, issue, newChecklistValue);
            
        }
        issueCount++;
	}
    log.warn("Import complete. " + issueCount + " issues affected")
    return Response.ok(new JsonBuilder(["Issue updated count:":issueCount])).build();
}